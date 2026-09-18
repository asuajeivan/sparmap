# agent/providers/whapi.py — Adaptador para Whapi.cloud

import os
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")

WHAPI_BASE = "https://gate.whapi.cloud"


class ProveedorWhapi(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Whapi.cloud."""

    def __init__(self):
        self.token = os.getenv("WHAPI_TOKEN")
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload JSON de Whapi.cloud."""
        try:
            body = await request.json()
        except Exception:
            logger.debug("Webhook Whapi: body no es JSON valido")
            return []

        logger.debug(f"Whapi webhook payload: {body}")

        mensajes = body.get("messages", [])
        resultado = []

        for msg in mensajes:
            es_propio = msg.get("from_me", False)
            texto = ""
            audio_id = ""

            if msg.get("type") == "text":
                texto = msg.get("text", {}).get("body", "")
            elif msg.get("type") == "interactive":
                texto = msg.get("interactive", {}).get("button_reply", {}).get("title", "")
            elif msg.get("type") in ("audio", "voice"):
                audio_data = msg.get("audio") or msg.get("voice") or {}
                audio_id = audio_data.get("id", "")

            telefono = msg.get("chat_id", "").replace("@s.whatsapp.net", "")

            if not telefono and msg.get("from"):
                telefono = msg["from"].replace("@s.whatsapp.net", "")

            resultado.append(MensajeEntrante(
                telefono=telefono,
                texto=texto,
                mensaje_id=msg.get("id", ""),
                es_propio=es_propio,
                audio_id=audio_id,
            ))

        return resultado

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envia mensaje de texto via Whapi.cloud."""
        if not self.token:
            logger.error("WHAPI_TOKEN no configurado — no se puede enviar mensaje")
            return False

        chat_id = telefono if "@" in telefono else f"{telefono}@s.whatsapp.net"

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{WHAPI_BASE}/messages/text",
                headers=self._headers(),
                json={"to": chat_id, "body": mensaje},
            )
            if r.status_code not in (200, 201):
                logger.error(f"Error Whapi enviar_mensaje: {r.status_code} — {r.text}")
                return False
            return True

    async def enviar_documento(self, telefono: str, ruta_archivo: str, nombre: str = "", caption: str = "") -> bool:
        """Envia un documento/PDF via Whapi.cloud."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — documento no enviado")
            return False

        import os
        from pathlib import Path

        archivo = Path(ruta_archivo)
        if not archivo.exists():
            logger.error(f"Archivo no encontrado: {ruta_archivo}")
            return False

        chat_id = telefono if "@" in telefono else f"{telefono}@s.whatsapp.net"
        filename = nombre or archivo.name

        async with httpx.AsyncClient() as client:
            with open(archivo, "rb") as f:
                r = await client.post(
                    f"{WHAPI_BASE}/messages/document",
                    headers={"Authorization": f"Bearer {self.token}"},
                    data={"to": chat_id, "caption": caption or ""},
                    files={"media": (filename, f, "application/pdf")},
                )
            if r.status_code not in (200, 201):
                logger.error(f"Error Whapi documento: {r.status_code} — {r.text}")
                return False
            logger.info(f"PDF enviado via Whapi a {telefono}: {filename}")
            return True

    async def descargar_media(self, media_id: str) -> bytes | None:
        """Descarga un archivo media de Whapi por su ID. Retorna bytes o None."""
        if not self.token or not media_id:
            return None

        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{WHAPI_BASE}/media/{media_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30.0,
            )
            if r.status_code == 200:
                logger.info(f"Media descargado: {media_id} ({len(r.content)} bytes)")
                return r.content
            logger.error(f"Error descargando media {media_id}: {r.status_code}")
            return None
