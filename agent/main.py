# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp.
Funciona con cualquier proveedor (Twilio, Meta) gracias a la capa de providers.
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor

# Seleccionar el cerebro según AI_PROVIDER y ODOO_ENABLED
ODOO_ENABLED = os.getenv("ODOO_ENABLED", "false").lower() == "true"
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic").lower()

if ODOO_ENABLED:
    if AI_PROVIDER == "gemini":
        from agent.brain_gemini import generar_respuesta
    else:
        from agent.brain_odoo import generar_respuesta
else:
    from agent.brain import generar_respuesta

load_dotenv()

# Configuración de logging según entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

# Proveedor de WhatsApp (se configura en .env con WHATSAPP_PROVIDER)
proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Número de WhatsApp del dueño/admin para recibir el reporte diario
REPORTE_TELEFONO = os.getenv("REPORTE_TELEFONO", "")

scheduler = AsyncIOScheduler()


async def _enviar_reporte_diario_programado():
    """Tarea programada: genera y envía el reporte diario por WhatsApp."""
    if not ODOO_ENABLED or not REPORTE_TELEFONO:
        return
    try:
        from agent.odoo.herramientas import obtener_datos_reporte_diario
        from agent.pdf_generator import generar_reporte_diario_pdf

        resultado = obtener_datos_reporte_diario()
        if not resultado.get("exito"):
            logger.error(f"Reporte diario programado falló: {resultado.get('error')}")
            return

        ruta_pdf = generar_reporte_diario_pdf(resultado["datos"])
        await proveedor.enviar_documento(
            REPORTE_TELEFONO, ruta_pdf,
            caption="Reporte Diario — SPARMAP, C.A.",
        )
        logger.info(f"Reporte diario enviado a {REPORTE_TELEFONO}")
    except Exception as e:
        logger.error(f"Error en reporte diario programado: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos y conexiones al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    logger.info(f"Proveedor de IA: {AI_PROVIDER}")

    # Inicializar integración Odoo si está activada
    if ODOO_ENABLED:
        from agent.odoo.conector import ConectorOdoo
        from agent.odoo.herramientas import inicializar as inicializar_odoo
        conector = ConectorOdoo()
        if conector.conectar():
            inicializar_odoo(conector)
            logger.info("Integración Odoo activa")
        else:
            logger.warning("Integración Odoo configurada pero no pudo conectar — revisar credenciales")

    # Programar reporte diario a las 7:00 PM hora Venezuela (UTC-4)
    if ODOO_ENABLED and REPORTE_TELEFONO:
        scheduler.add_job(
            _enviar_reporte_diario_programado,
            CronTrigger(hour=19, minute=0, timezone="America/Caracas"),
            id="reporte_diario",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(f"Reporte diario programado a las 7:00 PM VET → {REPORTE_TELEFONO}")

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title="AgentKit — WhatsApp AI Agent",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health_check():
    """Endpoint de salud para Railway/monitoreo."""
    return {"status": "ok", "service": "agentkit"}


@app.get("/output/{filename}")
async def servir_output(filename: str):
    """Sirve archivos de la carpeta output (PDFs de cotizaciones/reportes)."""
    from pathlib import Path
    filepath = Path(__file__).parent.parent / "output" / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(str(filepath), media_type="application/pdf", filename=filename)


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    """Verificación GET del webhook (requerido por Meta Cloud API, no-op para otros)."""
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp via el proveedor configurado.
    Procesa el mensaje, genera respuesta con Claude y la envía de vuelta.
    """
    try:
        # Parsear webhook — el proveedor normaliza el formato
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

            historial = await obtener_historial(msg.telefono)
            respuesta = await generar_respuesta(msg.texto, historial, telefono=msg.telefono)

            # Manejar respuesta con PDF (cotizacion)
            if isinstance(respuesta, dict):
                texto = respuesta.get("texto", "")
                pdf_path = respuesta.get("pdf_path")

                await guardar_mensaje(msg.telefono, "user", msg.texto)
                await guardar_mensaje(msg.telefono, "assistant", texto)

                # Enviar texto primero, luego el PDF
                await proveedor.enviar_mensaje(msg.telefono, texto)
                if pdf_path:
                    await proveedor.enviar_documento(
                        msg.telefono, pdf_path,
                        caption="Cotización SPARMAP, C.A.",
                    )
                logger.info(f"Respuesta + PDF a {msg.telefono}")
            else:
                await guardar_mensaje(msg.telefono, "user", msg.texto)
                await guardar_mensaje(msg.telefono, "assistant", respuesta)
                await proveedor.enviar_mensaje(msg.telefono, respuesta)
                logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reporte-diario")
async def reporte_diario():
    """
    Genera el reporte diario del negocio en PDF.
    Consulta Odoo para: ventas, cuentas por cobrar/pagar, stock bajo,
    top productos, proveedores activos.
    """
    if not ODOO_ENABLED:
        raise HTTPException(status_code=400, detail="Odoo no esta habilitado")

    try:
        from agent.odoo.herramientas import obtener_datos_reporte_diario
        from agent.pdf_generator import generar_reporte_diario_pdf

        resultado = obtener_datos_reporte_diario()
        if not resultado.get("exito"):
            raise HTTPException(status_code=500, detail=resultado.get("error", "Error consultando Odoo"))

        ruta_pdf = generar_reporte_diario_pdf(resultado["datos"])
        return FileResponse(
            ruta_pdf,
            media_type="application/pdf",
            filename=os.path.basename(ruta_pdf),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generando reporte diario: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reporte-diario/enviar/{telefono}")
async def enviar_reporte_diario(telefono: str):
    """Genera el reporte diario y lo envia por WhatsApp al numero indicado."""
    if not ODOO_ENABLED:
        raise HTTPException(status_code=400, detail="Odoo no esta habilitado")

    try:
        from agent.odoo.herramientas import obtener_datos_reporte_diario
        from agent.pdf_generator import generar_reporte_diario_pdf

        resultado = obtener_datos_reporte_diario()
        if not resultado.get("exito"):
            raise HTTPException(status_code=500, detail=resultado.get("error", "Error consultando Odoo"))

        ruta_pdf = generar_reporte_diario_pdf(resultado["datos"])

        enviado = await proveedor.enviar_documento(
            telefono, ruta_pdf,
            caption="Reporte Diario — SPARMAP, C.A.",
        )
        return {"status": "ok" if enviado else "error", "pdf": os.path.basename(ruta_pdf)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enviando reporte diario: {e}")
        raise HTTPException(status_code=500, detail=str(e))
