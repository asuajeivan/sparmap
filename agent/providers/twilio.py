# agent/providers/twilio.py — Adaptador para Twilio WhatsApp
# Generado por AgentKit

import os
import logging
import base64
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


class ProveedorTwilio(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Twilio."""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload form-encoded de Twilio."""
        form = await request.form()
        logger.debug(f"Twilio webhook payload: {dict(form)}")
        texto = form.get("Body", "")
        telefono = form.get("From", "").replace("whatsapp:", "")
        mensaje_id = form.get("MessageSid", "")
        if not texto:
            logger.debug(f"Webhook sin Body — probablemente status callback (SmsStatus={form.get('SmsStatus', form.get('MessageStatus', 'N/A'))})")
            return []
        return [MensajeEntrante(
            telefono=telefono,
            texto=texto,
            mensaje_id=mensaje_id,
            es_propio=False,
        )]

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Twilio API."""
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning("Variables de Twilio no configuradas")
            return False
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        auth = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}
        data = {
            "From": f"whatsapp:{self.phone_number}",
            "To": f"whatsapp:{telefono}",
            "Body": mensaje,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, data=data, headers=headers)
            if r.status_code != 201:
                logger.error(f"Error Twilio: {r.status_code} — {r.text}")
            return r.status_code == 201

    async def enviar_documento(self, telefono: str, ruta_archivo: str, nombre: str = "", caption: str = "") -> bool:
        """Envía un documento/PDF via Twilio usando MediaUrl."""
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning("Variables de Twilio no configuradas — documento no enviado")
            return False

        # Twilio requiere una URL pública para MediaUrl.
        # Si el archivo es local, lo enviamos como base64 en el body como fallback,
        # pero Twilio no soporta uploads directos — necesitamos servir el archivo.
        # Estrategia: usar el endpoint local /output/{filename} y la URL pública del servidor.
        import os
        from pathlib import Path

        archivo = Path(ruta_archivo)
        if not archivo.exists():
            logger.error(f"Archivo no encontrado: {ruta_archivo}")
            return False

        # Obtener la URL pública del servidor (Railway, ngrok, etc.)
        base_url = os.getenv("PUBLIC_URL", "").rstrip("/")
        if not base_url:
            logger.error("PUBLIC_URL no configurada en .env — no se puede enviar PDF por Twilio")
            return False

        media_url = f"{base_url}/output/{archivo.name}"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        auth = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}
        data = {
            "From": f"whatsapp:{self.phone_number}",
            "To": f"whatsapp:{telefono}",
            "MediaUrl": media_url,
        }
        if caption:
            data["Body"] = caption

        async with httpx.AsyncClient() as client:
            r = await client.post(url, data=data, headers=headers)
            if r.status_code != 201:
                logger.error(f"Error Twilio documento: {r.status_code} — {r.text}")
            else:
                logger.info(f"PDF enviado via Twilio a {telefono}: {archivo.name}")
            return r.status_code == 201
