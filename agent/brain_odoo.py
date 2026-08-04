# agent/brain_odoo.py — Cerebro del agente con integración Odoo
# Generado por AgentKit

"""
Versión avanzada de brain.py que conecta con Odoo via tool_use de Claude.

Flujo:
  1. Cliente escribe por WhatsApp
  2. Claude recibe el mensaje + historial + herramientas disponibles
  3. Claude decide si necesita consultar Odoo (stock, pedidos, etc.)
  4. Si sí → ejecutamos la herramienta → devolvemos resultado a Claude
  5. Claude genera la respuesta final en lenguaje natural
  6. El agente envía la respuesta por WhatsApp

Si ODOO_ENABLED=false en .env, funciona igual que brain.py normal (sin Odoo).
"""

import os
import json
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Bandera para activar/desactivar Odoo desde .env
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
        # Instrucción adicional para el uso de herramientas Odoo
        base += """

## Herramientas disponibles (Odoo ERP)
Tienes acceso al sistema de gestión empresarial (Odoo) del negocio.
Úsalas proactivamente cuando el cliente pregunte por:
- Productos, precios o disponibilidad → usa buscar_producto
- Estado de sus pedidos o historial → usa consultar_pedidos_cliente (primero busca al cliente)
- Facturas o saldos pendientes → usa consultar_facturas_pendientes (primero busca al cliente)
- Quiere que lo contacten para ventas → usa crear_lead

REGLAS para usar herramientas:
- Si el cliente pregunta por un producto específico, SIEMPRE busca en el sistema antes de responder
- Si el cliente menciona "mi pedido" o "mi factura", busca primero por su teléfono
- Nunca inventes datos de stock, precios o pedidos — consúltalos en el sistema
- Si una búsqueda no retorna resultados, díselo al cliente honestamente
- Usa el resultado de las herramientas para dar respuestas precisas y útiles
"""
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


# ─── Generación de respuesta ─────────────────────────────────────────────────

async def generar_respuesta(mensaje: str, historial: list[dict], telefono: str = None) -> str:
    """
    Genera una respuesta usando Claude API, con soporte opcional para Odoo.

    Args:
        mensaje:   El mensaje nuevo del usuario
        historial: Mensajes anteriores de la conversación
        telefono:  Número del cliente (para buscar en Odoo si es necesario)

    Returns:
        La respuesta final generada por Claude
    """
    if not mensaje or len(mensaje.strip()) < 2:
        return _mensaje_fallback()

    # Construir lista de mensajes para Claude
    mensajes = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in historial
    ]
    mensajes.append({"role": "user", "content": mensaje})

    # Herramientas disponibles (solo si Odoo está activado)
    herramientas = []
    if ODOO_ENABLED:
        from agent.odoo.herramientas import HERRAMIENTAS_CLAUDE
        herramientas = HERRAMIENTAS_CLAUDE

    try:
        respuesta = await _llamar_claude(mensajes, herramientas, telefono)
        return respuesta
    except Exception as e:
        logger.error(f"Error generando respuesta: {e}")
        return _mensaje_error()


async def _llamar_claude(
    mensajes: list[dict],
    herramientas: list[dict],
    telefono: str = None,
    max_iteraciones: int = 5,
) -> str:
    """
    Loop de tool_use: llama a Claude, ejecuta herramientas si las pide,
    y repite hasta obtener una respuesta de texto final.

    max_iteraciones previene loops infinitos si algo sale mal.
    """
    system_prompt = _cargar_system_prompt()
    mensajes_actuales = list(mensajes)

    for iteracion in range(max_iteraciones):
        kwargs = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": mensajes_actuales,
        }
        if herramientas:
            kwargs["tools"] = herramientas

        response = await client.messages.create(**kwargs)

        # ── Respuesta de texto final ──────────────────────────────────────────
        if response.stop_reason == "end_turn":
            texto = next(
                (bloque.text for bloque in response.content if hasattr(bloque, "text")),
                None
            )
            if texto:
                return texto
            # Si no hay texto, algo salió mal
            logger.warning("Claude respondió sin texto en end_turn")
            return _mensaje_error()

        # ── Claude quiere usar una herramienta ────────────────────────────────
        if response.stop_reason == "tool_use":
            # Puede haber múltiples tool_use en un solo mensaje (Claude los agrupa)
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                logger.warning("stop_reason=tool_use pero sin bloques tool_use")
                break

            # Agregar la respuesta de Claude (con los tool_use) al historial
            mensajes_actuales.append({"role": "assistant", "content": response.content})

            # Ejecutar cada herramienta y recopilar resultados
            resultados_herramientas = []
            for tool_use in tool_uses:
                nombre = tool_use.name
                argumentos = tool_use.input

                # Si el cliente no dio su nombre pero tenemos el teléfono, inyectarlo
                if nombre == "buscar_cliente_por_telefono" and "telefono" not in argumentos and telefono:
                    argumentos["telefono"] = telefono

                logger.info(f"Ejecutando herramienta: {nombre}({json.dumps(argumentos, ensure_ascii=False)})")

                from agent.odoo.herramientas import ejecutar_herramienta
                resultado = ejecutar_herramienta(nombre, argumentos)

                logger.info(f"Resultado {nombre}: exito={resultado.get('exito')}")

                resultados_herramientas.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(resultado, ensure_ascii=False, default=str),
                })

            # Devolver los resultados a Claude para que genere la respuesta final
            mensajes_actuales.append({
                "role": "user",
                "content": resultados_herramientas,
            })

            # Siguiente iteración → Claude procesa los resultados
            continue

        # ── Stop reason inesperado ────────────────────────────────────────────
        logger.warning(f"Stop reason inesperado de Claude: {response.stop_reason}")
        break

    logger.error("Se alcanzó el máximo de iteraciones en el loop de herramientas")
    return _mensaje_error()
