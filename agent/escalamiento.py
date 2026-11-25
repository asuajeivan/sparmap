# agent/escalamiento.py — Identidad del agente y aviso al equipo de ventas
#
# Cuando el agente no puede resolver una consulta (producto no encontrado,
# agotado, asesoria tecnica, el cliente pide un vendedor, etc.) no basta con
# darle los numeros al cliente: tambien se le avisa por WhatsApp a un vendedor
# para que tome el caso. Los vendedores se asignan por turnos (round-robin).

import os
import time
import logging
from itertools import cycle

logger = logging.getLogger("agentkit")

# ── Identidad del agente ─────────────────────────────────────────────────────

NOMBRE_AGENTE = os.getenv("AGENTE_NOMBRE", "Chispa").strip() or "Chispa"

PRESENTACION = (
    f"Soy *{NOMBRE_AGENTE}*, el asistente virtual (inteligencia artificial) de "
    "*SPARMAP, C.A.* Te respondo al instante, y si hace falta te paso con "
    "uno de nuestros asesores."
)

# ── Vendedores ───────────────────────────────────────────────────────────────

# Formato: "584120399694,584120402832" (solo digitos, con codigo de pais)
_VENDEDORES = [
    t.strip().replace("+", "").replace("-", "").replace(" ", "")
    for t in os.getenv("VENDEDORES_TELEFONOS", "584120399694,584120402832").split(",")
    if t.strip()
]
_turno = cycle(_VENDEDORES) if _VENDEDORES else None

# Evita avisar varias veces por el mismo cliente en poco tiempo
_VENTANA_DEDUP_SEG = 30 * 60
_ultimo_aviso: dict[str, tuple[float, str]] = {}  # telefono_cliente → (timestamp, vendedor)


def _formatear_numero(numero: str) -> str:
    """'584120399694' → '+58 412-0399694'."""
    if len(numero) == 12 and numero.startswith("58"):
        return f"+58 {numero[2:5]}-{numero[5:]}"
    return f"+{numero}"


async def notificar_equipo_ventas(
    telefono_cliente: str,
    consulta: str,
    motivo: str,
    cliente_nombre: str = "",
) -> dict:
    """
    Envia un aviso por WhatsApp a un vendedor (por turnos) con la consulta
    que el agente no pudo resolver. Retorna el vendedor asignado.
    """
    if not _turno:
        logger.warning("VENDEDORES_TELEFONOS vacio — no se pudo escalar la consulta")
        return {"exito": False, "error": "No hay vendedores configurados."}

    cliente = (telefono_cliente or "").split("@")[0]
    ahora = time.time()

    # Si ya se aviso hace poco por este cliente, reutilizar el mismo vendedor
    previo = _ultimo_aviso.get(cliente)
    vendedor = previo[1] if previo and ahora - previo[0] < _VENTANA_DEDUP_SEG else next(_turno)

    texto = (
        "*Consulta para atender* (asignada por el agente virtual)\n\n"
        f"*Cliente:* {cliente_nombre or 'Sin nombre'}\n"
        f"*WhatsApp:* +{cliente}\n"
        f"*Motivo:* {motivo}\n"
        f"*Consulta:* {consulta}\n\n"
        f"Escribele directo: https://wa.me/{cliente}"
    )

    from agent.providers import obtener_proveedor
    try:
        enviado = await obtener_proveedor().enviar_mensaje(vendedor, texto)
    except Exception as e:
        logger.error(f"Error notificando al vendedor {vendedor}: {e}")
        enviado = False

    if not enviado:
        return {"exito": False, "error": "No se pudo avisar al vendedor."}

    _ultimo_aviso[cliente] = (ahora, vendedor)
    logger.info(f"Consulta de {cliente} escalada al vendedor {vendedor} ({motivo})")
    return {
        "exito": True,
        "datos": {"asesor_asignado": _formatear_numero(vendedor)},
        "mensaje": "El asesor ya fue notificado y contactara al cliente.",
    }


# ── Definicion de herramienta para el modelo (formato Claude) ───────────────

HERRAMIENTA_NOTIFICAR = {
    "name": "notificar_equipo_ventas",
    "description": (
        "Avisa por WhatsApp a un vendedor de SPARMAP para que contacte al cliente. "
        "USALA SIEMPRE que no puedas resolver la consulta: producto no encontrado o agotado, "
        "asesoria tecnica, servicios de ingenieria/instalaciones, el cliente pide hablar con "
        "una persona, reclamos, o cualquier tema fuera de tu alcance. "
        "El telefono del cliente se agrega solo. Devuelve el numero del asesor asignado."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "consulta": {
                "type": "string",
                "description": "Resumen claro de lo que el cliente necesita (ej: 'Contactor 12A', 'prensa estopa 1/2')",
            },
            "motivo": {
                "type": "string",
                "description": "Por que se escala: 'producto no encontrado', 'producto agotado', 'asesoria tecnica', 'pide vendedor', 'otro'",
            },
            "cliente_nombre": {
                "type": "string",
                "description": "Nombre del cliente si se conoce",
            },
        },
        "required": ["consulta", "motivo"],
    },
}
