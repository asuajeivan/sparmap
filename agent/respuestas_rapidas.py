# agent/respuestas_rapidas.py — Respuestas locales sin consumir API
#
# Intercepta mensajes simples (saludos, horario, ubicacion, gracias, etc.)
# y devuelve una respuesta predefinida. Ahorra creditos de IA al no enviar
# estos mensajes triviales a Claude/Gemini.
#
# Si retorna None, el mensaje se procesa normalmente via la API.

import re
from datetime import datetime, timezone, timedelta

# Zona horaria Venezuela (UTC-4)
_VET = timezone(timedelta(hours=-4))


def _saludo_por_hora() -> str:
    hora = datetime.now(_VET).hour
    if 5 <= hora < 12:
        return "Buenos dias"
    elif 12 <= hora < 18:
        return "Buenas tardes"
    return "Buenas noches"


# ── Respuestas predefinidas ──────────────────────────────────────────────────

_BIENVENIDA = (
    "{saludo}! Bienvenido/a a *SPARMAP, C.A.* — tu aliado en suministros "
    "electricos e ingenieria en Acarigua.\n\n"
    "Aqui puedes consultar disponibilidad, precios y generar cotizaciones "
    "al instante.\n\n"
    "Tambien puedes ver nuestro catalogo completo en linea:\n"
    "https://sparmap.com.ve/shop\n\n"
    "Si necesitas atencion personalizada, nuestro equipo de ventas esta "
    "para ayudarte:\n"
    "*Asesor 1:* +58 412-0399694\n"
    "*Asesor 2:* +58 412-0402832\n\n"
    "En que te puedo ayudar hoy?"
)

_HORARIO = (
    "Nuestro horario de atencion en tienda es:\n"
    "*Lun - Vie:* 8:00 am a 5:00 pm\n"
    "*Sabado:* 8:00 am a 12:00 pm\n"
    "*Domingo:* Cerrado\n\n"
    "Por este chat te atendemos las 24 horas."
)

_UBICACION = (
    "Estamos ubicados en:\n"
    "Local 05, C.C Rosita, entre Av 39 y 40, C. 31\n"
    "Acarigua 3301, Portuguesa, Venezuela\n\n"
    "Visitanos en horario de tienda o escribenos por aqui."
)

_GRACIAS = (
    "Con gusto! Si necesitas algo mas, aqui estamos.\n\n"
    "Tambien puedes explorar nuestro catalogo en:\n"
    "https://sparmap.com.ve/shop"
)

_CONTACTO = (
    "Puedes comunicarte con nuestro equipo de ventas:\n"
    "*Asesor 1:* +58 412-0399694\n"
    "*Asesor 2:* +58 412-0402832\n\n"
    "O visitanos en tienda: Local 05, C.C Rosita, Acarigua."
)

# ── Patrones de deteccion ────────────────────────────────────────────────────

# Normalizamos: minusculas, sin acentos comunes, sin puntuacion
def _normalizar(texto: str) -> str:
    t = texto.lower().strip()
    t = re.sub(r'[¿?!¡.,;:\-_\'"()]+', '', t)
    t = t.replace('á', 'a').replace('é', 'e').replace('í', 'i')
    t = t.replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
    return t.strip()


_PATRONES_SALUDO = {
    "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
    "buen dia", "hey", "hi", "hello", "alo", "saludos", "que tal",
    "como estas", "epa", "holi",
}

_PATRONES_HORARIO = {
    "horario", "hora", "que hora abren", "a que hora abren",
    "a que hora cierran", "estan abiertos", "abren hoy",
    "horario de atencion", "cuando abren", "cuando cierran",
}

_PATRONES_UBICACION = {
    "donde estan", "donde quedan", "direccion", "ubicacion",
    "como llego", "donde es", "donde queda la tienda",
}

_PATRONES_GRACIAS = {
    "gracias", "grax", "thanks", "vale gracias", "muchas gracias",
    "ok gracias", "listo gracias", "perfecto gracias", "genial gracias",
    "chevere gracias",
}

_PATRONES_CONTACTO = {
    "numero", "telefono", "contacto", "como los contacto",
    "numero de telefono", "whatsapp", "vendedor", "asesor",
}


def _coincide(texto_normalizado: str, patrones: set) -> bool:
    """Verifica si el texto normalizado coincide con alguno de los patrones."""
    if texto_normalizado in patrones:
        return True
    # Tambien verificar si el texto completo CONTIENE un patron
    # pero solo si el mensaje es corto (evitar falsos positivos)
    if len(texto_normalizado.split()) <= 5:
        for p in patrones:
            if p in texto_normalizado:
                return True
    return False


def intentar_respuesta_rapida(mensaje: str, historial: list[dict]) -> str | None:
    """
    Intenta responder un mensaje sin llamar a la API.

    Args:
        mensaje:   Texto del usuario
        historial: Historial de la conversacion (para saber si es primer mensaje)

    Returns:
        str con la respuesta si se pudo resolver localmente, None si no.
    """
    norm = _normalizar(mensaje)

    # Mensajes muy cortos o solo emojis → no interceptar, dejar que la IA maneje
    if len(norm) < 2:
        return None

    # Saludo → bienvenida (solo si no hay historial o historial muy corto)
    if _coincide(norm, _PATRONES_SALUDO):
        if len(historial) <= 2:
            return _BIENVENIDA.format(saludo=_saludo_por_hora())
        # Si ya hay conversacion, un saludo corto sin bienvenida completa
        return f"{_saludo_por_hora()}! En que te puedo ayudar?"

    # Horario
    if _coincide(norm, _PATRONES_HORARIO):
        return _HORARIO

    # Ubicacion
    if _coincide(norm, _PATRONES_UBICACION):
        return _UBICACION

    # Gracias
    if _coincide(norm, _PATRONES_GRACIAS):
        return _GRACIAS

    # Contacto / vendedores
    if _coincide(norm, _PATRONES_CONTACTO):
        return _CONTACTO

    # No es un mensaje simple → dejar que la API lo maneje
    return None
