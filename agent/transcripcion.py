# agent/transcripcion.py — Transcripción de audio con Gemini

import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


async def transcribir_audio(audio_bytes: bytes) -> str:
    """
    Transcribe audio a texto usando Gemini.
    Recibe bytes de audio (ogg/opus de WhatsApp) y devuelve el texto transcrito.
    """
    if not audio_bytes:
        return ""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY no configurada — no se puede transcribir audio")
        return ""

    try:
        from google.genai import types

        client = _get_client()
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg")

        response = await client.aio.models.generate_content(
            model=model,
            contents=[
                types.Content(role="user", parts=[
                    audio_part,
                    types.Part.from_text(
                        text="Transcribe este audio de WhatsApp a texto en español. "
                             "Devuelve SOLO la transcripción, sin explicaciones ni formato adicional."
                    ),
                ]),
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=500,
                temperature=0.1,
            ),
        )

        texto = response.text.strip() if response.text else ""
        if texto:
            logger.info(f"Transcripción exitosa ({len(audio_bytes)} bytes -> {len(texto)} chars)")
        else:
            logger.warning("Gemini devolvió transcripción vacía")
        return texto

    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}")
        return ""
