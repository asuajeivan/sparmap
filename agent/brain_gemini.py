# agent/brain_gemini.py — Cerebro del agente con Gemini + Odoo

"""
Versión Gemini de brain_odoo.py. Mismo flujo de tool_use pero usando
Google Gemini Flash en lugar de Claude.

Flujo idéntico:
  1. Cliente escribe por WhatsApp
  2. Gemini recibe el mensaje + historial + herramientas disponibles
  3. Gemini decide si necesita consultar Odoo (stock, pedidos, etc.)
  4. Si sí → ejecutamos la herramienta → devolvemos resultado a Gemini
  5. Gemini genera la respuesta final en lenguaje natural
  6. El agente envía la respuesta por WhatsApp
"""

import os
import json
import yaml
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

ODOO_ENABLED = os.getenv("ODOO_ENABLED", "false").lower() == "true"


# ─── Carga de configuración ──────────────────────────────────────────────────

def _cargar_config_prompts() -> dict:
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def _cargar_system_prompt() -> str:
    config = _cargar_config_prompts()
    base = config.get("system_prompt", "Eres un asistente útil. Responde en español.")

    if ODOO_ENABLED:
        base += "\nTienes acceso al inventario de Odoo. Usa buscar_producto para productos especificos, obtener_catalogo para listas por categoria."
    return base


def _mensaje_error() -> str:
    return _cargar_config_prompts().get(
        "error_message",
        "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos."
    )


def _mensaje_fallback() -> str:
    return _cargar_config_prompts().get(
        "fallback_message",
        "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?"
    )


# ─── Conversión de herramientas Claude → Gemini ─────────────────────────────

def _convertir_herramientas_a_gemini(herramientas_claude: list[dict]) -> list[types.Tool]:
    """
    Convierte la definición de herramientas del formato Claude al formato Gemini.
    Claude: {name, description, input_schema: {type, properties, required}}
    Gemini: types.Tool con function_declarations
    """
    if not herramientas_claude:
        return []

    declarations = []
    for h in herramientas_claude:
        schema = h.get("input_schema", {})
        properties = {}
        for prop_name, prop_def in schema.get("properties", {}).items():
            prop_type = prop_def.get("type", "string").upper()
            type_map = {
                "STRING": "STRING",
                "INTEGER": "INTEGER",
                "NUMBER": "NUMBER",
                "BOOLEAN": "BOOLEAN",
                "ARRAY": "ARRAY",
                "OBJECT": "OBJECT",
            }
            gemini_type = type_map.get(prop_type, "STRING")

            prop_schema = {
                "type": gemini_type,
                "description": prop_def.get("description", ""),
            }

            # Manejar arrays con items
            if gemini_type == "ARRAY" and "items" in prop_def:
                items_def = prop_def["items"]
                items_type = items_def.get("type", "string").upper()
                item_schema = {"type": type_map.get(items_type, "STRING")}
                if "properties" in items_def:
                    item_schema["properties"] = {}
                    for ip_name, ip_def in items_def["properties"].items():
                        ip_type = ip_def.get("type", "string").upper()
                        item_schema["properties"][ip_name] = {
                            "type": type_map.get(ip_type, "STRING"),
                            "description": ip_def.get("description", ""),
                        }
                    if "required" in items_def:
                        item_schema["required"] = items_def["required"]
                prop_schema["items"] = item_schema

            properties[prop_name] = prop_schema

        decl = {
            "name": h["name"],
            "description": h.get("description", ""),
            "parameters": {
                "type": "OBJECT",
                "properties": properties,
            },
        }
        if "required" in schema:
            decl["parameters"]["required"] = schema["required"]

        declarations.append(decl)

    return [types.Tool(function_declarations=declarations)]


# ─── Generación de respuesta ─────────────────────────────────────────────────

async def generar_respuesta(mensaje: str, historial: list[dict], telefono: str = None) -> str | dict:
    """
    Genera una respuesta usando Gemini API, con soporte opcional para Odoo.
    Interfaz idéntica a brain_odoo.generar_respuesta.
    """
    if not mensaje or len(mensaje.strip()) < 2:
        return _mensaje_fallback()

    # Convertir historial al formato Gemini
    contenidos = []
    for msg in historial:
        role = "user" if msg["role"] == "user" else "model"
        contenidos.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
    contenidos.append(types.Content(role="user", parts=[types.Part.from_text(text=mensaje)]))

    # Herramientas
    herramientas_gemini = []
    if ODOO_ENABLED:
        from agent.odoo.herramientas import HERRAMIENTAS_CLAUDE
        herramientas_gemini = _convertir_herramientas_a_gemini(HERRAMIENTAS_CLAUDE)

    try:
        respuesta = await _llamar_gemini(contenidos, herramientas_gemini, telefono)
        return respuesta
    except Exception as e:
        logger.error(f"Error generando respuesta: {e}")
        return _mensaje_error()


async def _llamar_gemini(
    contenidos: list,
    herramientas: list,
    telefono: str = None,
    max_iteraciones: int = 5,
) -> str | dict:
    """
    Loop de function calling: llama a Gemini, ejecuta herramientas si las pide,
    y repite hasta obtener una respuesta de texto final.
    """
    system_prompt = _cargar_system_prompt()
    contenidos_actuales = list(contenidos)
    pdf_path = None

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=1024,
        temperature=0.7,
    )
    if herramientas:
        config.tools = herramientas

    for iteracion in range(max_iteraciones):
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=contenidos_actuales,
            config=config,
        )

        # Verificar si hay function calls
        function_calls = []
        text_parts = []
        for part in response.candidates[0].content.parts:
            if part.function_call:
                function_calls.append(part.function_call)
            elif part.text:
                text_parts.append(part.text)

        # ── Sin function calls → respuesta final ────────────────────────────
        if not function_calls:
            texto = " ".join(text_parts).strip()
            if texto:
                if pdf_path:
                    return {"texto": texto, "pdf_path": pdf_path}
                return texto
            logger.warning("Gemini respondió sin texto")
            return _mensaje_error()

        # ── Gemini quiere usar herramientas ──────────────────────────────────
        # Agregar la respuesta del modelo al historial
        contenidos_actuales.append(response.candidates[0].content)

        function_responses = []
        for fc in function_calls:
            nombre = fc.name
            argumentos = dict(fc.args) if fc.args else {}

            if nombre == "buscar_cliente_por_telefono" and "telefono" not in argumentos and telefono:
                argumentos["telefono"] = telefono

            if nombre == "generar_cotizacion" and telefono:
                argumentos.setdefault("cliente_telefono", telefono)

            logger.info(f"Ejecutando herramienta: {nombre}({json.dumps(argumentos, ensure_ascii=False)})")

            from agent.odoo.herramientas import ejecutar_herramienta
            resultado = ejecutar_herramienta(nombre, argumentos)

            logger.info(f"Resultado {nombre}: exito={resultado.get('exito')}")

            if nombre == "generar_cotizacion" and resultado.get("exito") and resultado.get("ruta_pdf"):
                pdf_path = resultado["ruta_pdf"]

            function_responses.append(
                types.Part.from_function_response(
                    name=nombre,
                    response={"result": json.dumps(resultado, ensure_ascii=False, default=str)},
                )
            )

        contenidos_actuales.append(
            types.Content(role="user", parts=function_responses)
        )
        continue

    logger.error("Se alcanzó el máximo de iteraciones en el loop de herramientas")
    return _mensaje_error()
