# agent/odoo/herramientas.py — Operaciones de negocio sobre Odoo
# Generado por AgentKit

"""
Todas las acciones que el agente puede ejecutar sobre Odoo.
Cada función retorna un dict con 'exito' (bool) y 'datos' o 'error'.

El agente de IA (brain_odoo.py) llama estas funciones según
lo que el cliente pide por WhatsApp.
"""

import logging
from agent.odoo.conector import ConectorOdoo

logger = logging.getLogger("agentkit")

# Instancia global del conector (se inicializa desde main.py)
_odoo: ConectorOdoo | None = None


def inicializar(conector: ConectorOdoo):
    """Registra el conector Odoo que usarán todas las herramientas."""
    global _odoo
    _odoo = conector


def _sin_odoo() -> dict:
    return {"exito": False, "error": "Integración con Odoo no disponible en este momento."}


# ═══════════════════════════════════════════════════════════════
# PRODUCTOS Y CATALOGO
# ═══════════════════════════════════════════════════════════════

def buscar_producto(nombre: str) -> dict:
    """
    Busca productos en el catálogo por nombre (búsqueda flexible).
    Retorna hasta 5 resultados con precio y stock disponible.
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    resultados = _odoo.llamar(
        "product.product", "search_read",
        [[["name", "ilike", nombre], ["active", "=", True], ["sale_ok", "=", True]]],
        {
            "fields": ["id", "name", "list_price", "qty_available", "default_code", "description_sale"],
            "limit": 5,
            "order": "name asc",
        }
    )

    if resultados is None:
        return {"exito": False, "error": "No se pudo consultar el catálogo."}
    if not resultados:
        return {"exito": True, "datos": [], "mensaje": f"No encontré productos con el nombre '{nombre}'."}

    productos = [
        {
            "id": p["id"],
            "nombre": p["name"],
            "codigo": p.get("default_code") or "—",
            "precio": p["list_price"],
            "stock": p["qty_available"],
            "descripcion": p.get("description_sale") or "",
        }
        for p in resultados
    ]
    return {"exito": True, "datos": productos}


def obtener_producto_por_id(producto_id: int) -> dict:
    """Obtiene los detalles completos de un producto por su ID."""
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    resultado = _odoo.llamar(
        "product.product", "read",
        [[producto_id]],
        {"fields": ["id", "name", "list_price", "qty_available", "virtual_available", "default_code", "description_sale"]}
    )

    if not resultado:
        return {"exito": False, "error": "Producto no encontrado."}
    p = resultado[0]
    return {
        "exito": True,
        "datos": {
            "id": p["id"],
            "nombre": p["name"],
            "codigo": p.get("default_code") or "—",
            "precio": p["list_price"],
            "stock_disponible": p["qty_available"],
            "stock_futuro": p.get("virtual_available", 0),
            "descripcion": p.get("description_sale") or "",
        }
    }


# ═══════════════════════════════════════════════════════════════
# CLIENTES / PARTNERS
# ═══════════════════════════════════════════════════════════════

def buscar_cliente_por_telefono(telefono: str) -> dict:
    """
    Busca un cliente en Odoo por número de teléfono.
    Útil para identificar quién está escribiendo por WhatsApp.
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    # Normalizar teléfono: quitar + y espacios para buscar variantes
    telefono_limpio = telefono.replace("+", "").replace(" ", "").replace("-", "")

    resultados = _odoo.llamar(
        "res.partner", "search_read",
        [[
            "|", "|",
            ["phone", "like", telefono_limpio[-9:]],   # últimos 9 dígitos
            ["mobile", "like", telefono_limpio[-9:]],
            ["phone", "=", telefono],
        ]],
        {"fields": ["id", "name", "phone", "mobile", "email", "street", "city"], "limit": 1}
    )

    if not resultados:
        return {"exito": True, "datos": None, "mensaje": "Cliente no encontrado en el sistema."}

    c = resultados[0]
    return {
        "exito": True,
        "datos": {
            "id": c["id"],
            "nombre": c["name"],
            "telefono": c.get("phone") or c.get("mobile") or "—",
            "email": c.get("email") or "—",
            "direccion": f"{c.get('street', '')} {c.get('city', '')}".strip() or "—",
        }
    }


def crear_lead(nombre_contacto: str, telefono: str, interes: str, notas: str = "") -> dict:
    """
    Registra un lead/oportunidad en el CRM de Odoo.
    Úsalo cuando un cliente nuevo pide información o quiere que lo contacten.
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    lead_id = _odoo.llamar(
        "crm.lead", "create",
        [{
            "name": f"WhatsApp: {nombre_contacto} — {interes[:50]}",
            "phone": telefono,
            "description": f"Interés: {interes}\n\nNotas: {notas}".strip(),
            "type": "lead",
        }]
    )

    if not lead_id:
        return {"exito": False, "error": "No se pudo registrar el lead."}
    return {
        "exito": True,
        "datos": {"lead_id": lead_id},
        "mensaje": f"Lead registrado con ID {lead_id}. El equipo de ventas se comunicará contigo pronto."
    }


# ═══════════════════════════════════════════════════════════════
# PEDIDOS DE VENTA
# ═══════════════════════════════════════════════════════════════

def consultar_pedidos_cliente(partner_id: int, limite: int = 5) -> dict:
    """
    Retorna los últimos pedidos de un cliente.
    Requiere conocer el partner_id del cliente en Odoo.
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    pedidos = _odoo.llamar(
        "sale.order", "search_read",
        [[["partner_id", "=", partner_id]]],
        {
            "fields": ["name", "state", "amount_total", "date_order", "commitment_date"],
            "order": "date_order desc",
            "limit": limite,
        }
    )

    if pedidos is None:
        return {"exito": False, "error": "No se pudo consultar los pedidos."}

    # Traducir estados de Odoo a español legible
    estados = {
        "draft": "Borrador",
        "sent": "Presupuesto enviado",
        "sale": "Confirmado",
        "done": "Completado",
        "cancel": "Cancelado",
    }

    datos = [
        {
            "numero": p["name"],
            "estado": estados.get(p["state"], p["state"]),
            "total": p["amount_total"],
            "fecha": str(p["date_order"])[:10] if p.get("date_order") else "—",
            "entrega": str(p["commitment_date"])[:10] if p.get("commitment_date") else "—",
        }
        for p in pedidos
    ]
    return {"exito": True, "datos": datos}


def crear_pedido_borrador(partner_id: int, lineas: list[dict]) -> dict:
    """
    Crea un pedido de venta en estado borrador en Odoo.

    Args:
        partner_id: ID del cliente en Odoo
        lineas: Lista de productos, ej:
                [{"product_id": 42, "cantidad": 2}, ...]

    Retorna el ID y número del pedido creado.
    IMPORTANTE: El pedido queda en borrador — un vendedor debe confirmarlo.
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    order_lines = [
        (0, 0, {
            "product_id": linea["product_id"],
            "product_uom_qty": linea.get("cantidad", 1),
        })
        for linea in lineas
    ]

    order_id = _odoo.llamar(
        "sale.order", "create",
        [{"partner_id": partner_id, "order_line": order_lines}]
    )

    if not order_id:
        return {"exito": False, "error": "No se pudo crear el pedido."}

    # Leer el número asignado
    pedido = _odoo.llamar(
        "sale.order", "read",
        [[order_id]],
        {"fields": ["name", "amount_total"]}
    )

    numero = pedido[0]["name"] if pedido else f"ID-{order_id}"
    total = pedido[0]["amount_total"] if pedido else 0

    return {
        "exito": True,
        "datos": {"order_id": order_id, "numero": numero, "total": total},
        "mensaje": f"Pedido {numero} creado por ${total:,.2f}. Está en revisión — un asesor lo confirmará pronto."
    }


# ═══════════════════════════════════════════════════════════════
# FACTURAS
# ═══════════════════════════════════════════════════════════════

def consultar_facturas_pendientes(partner_id: int) -> dict:
    """
    Retorna las facturas pendientes de pago de un cliente.
    Útil para recordatorios de cobro o consultas de saldo.
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    facturas = _odoo.llamar(
        "account.move", "search_read",
        [[
            ["partner_id", "=", partner_id],
            ["move_type", "=", "out_invoice"],
            ["payment_state", "in", ["not_paid", "partial"]],
            ["state", "=", "posted"],
        ]],
        {
            "fields": ["name", "invoice_date_due", "amount_residual", "payment_state"],
            "order": "invoice_date_due asc",
            "limit": 10,
        }
    )

    if facturas is None:
        return {"exito": False, "error": "No se pudo consultar las facturas."}
    if not facturas:
        return {"exito": True, "datos": [], "mensaje": "No tienes facturas pendientes."}

    estados_pago = {
        "not_paid": "Sin pagar",
        "partial": "Pago parcial",
    }

    datos = [
        {
            "numero": f["name"],
            "vencimiento": str(f["invoice_date_due"]) if f.get("invoice_date_due") else "—",
            "saldo_pendiente": f["amount_residual"],
            "estado": estados_pago.get(f["payment_state"], f["payment_state"]),
        }
        for f in facturas
    ]
    total_pendiente = sum(f["amount_residual"] for f in facturas)
    return {"exito": True, "datos": datos, "total_pendiente": total_pendiente}


# ═══════════════════════════════════════════════════════════════
# DEFINICIONES DE HERRAMIENTAS PARA CLAUDE (tool_use)
# ═══════════════════════════════════════════════════════════════

HERRAMIENTAS_CLAUDE = [
    {
        "name": "buscar_producto",
        "description": (
            "Busca productos en el catálogo de la empresa por nombre. "
            "Úsalo cuando el cliente pregunta por un producto, su precio, "
            "disponibilidad, si hay stock, o qué productos ofrece la empresa."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre o parte del nombre del producto a buscar"
                }
            },
            "required": ["nombre"]
        }
    },
    {
        "name": "buscar_cliente_por_telefono",
        "description": (
            "Busca si el cliente que está escribiendo ya existe en el sistema. "
            "Úsalo al inicio de la conversación o cuando necesites datos del cliente "
            "para consultar sus pedidos o facturas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "telefono": {
                    "type": "string",
                    "description": "Número de teléfono del cliente (con o sin código de país)"
                }
            },
            "required": ["telefono"]
        }
    },
    {
        "name": "consultar_pedidos_cliente",
        "description": (
            "Consulta los últimos pedidos de un cliente. "
            "Úsalo cuando el cliente pregunta por el estado de su pedido, "
            "su historial de compras o cuándo llega su pedido."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "partner_id": {
                    "type": "integer",
                    "description": "ID del cliente en Odoo (obtenido con buscar_cliente_por_telefono)"
                }
            },
            "required": ["partner_id"]
        }
    },
    {
        "name": "consultar_facturas_pendientes",
        "description": (
            "Consulta las facturas pendientes de pago de un cliente. "
            "Úsalo cuando el cliente pregunta cuánto debe, "
            "qué facturas tiene pendientes o su saldo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "partner_id": {
                    "type": "integer",
                    "description": "ID del cliente en Odoo (obtenido con buscar_cliente_por_telefono)"
                }
            },
            "required": ["partner_id"]
        }
    },
    {
        "name": "crear_lead",
        "description": (
            "Registra un lead en el CRM cuando un cliente nuevo muestra interés "
            "o quiere que lo contacten. Úsalo cuando el cliente pide información "
            "de ventas, quiere una cotización formal o pide que lo llamen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre_contacto": {
                    "type": "string",
                    "description": "Nombre del cliente o persona de contacto"
                },
                "telefono": {
                    "type": "string",
                    "description": "Número de teléfono del cliente"
                },
                "interes": {
                    "type": "string",
                    "description": "Qué producto o servicio le interesa al cliente"
                },
                "notas": {
                    "type": "string",
                    "description": "Información adicional relevante de la conversación"
                }
            },
            "required": ["nombre_contacto", "telefono", "interes"]
        }
    },
]


# ─── Mapa de nombre → función para ejecutar desde brain_odoo.py ─────────────

MAPA_HERRAMIENTAS = {
    "buscar_producto": lambda args: buscar_producto(args["nombre"]),
    "buscar_cliente_por_telefono": lambda args: buscar_cliente_por_telefono(args["telefono"]),
    "consultar_pedidos_cliente": lambda args: consultar_pedidos_cliente(args["partner_id"]),
    "consultar_facturas_pendientes": lambda args: consultar_facturas_pendientes(args["partner_id"]),
    "crear_lead": lambda args: crear_lead(
        args["nombre_contacto"],
        args["telefono"],
        args["interes"],
        args.get("notas", "")
    ),
}


def ejecutar_herramienta(nombre: str, argumentos: dict) -> dict:
    """
    Ejecuta la herramienta indicada con los argumentos dados.
    Llamado por brain_odoo.py cuando Claude decide usar una herramienta.
    """
    if nombre not in MAPA_HERRAMIENTAS:
        return {"exito": False, "error": f"Herramienta desconocida: {nombre}"}
    try:
        return MAPA_HERRAMIENTAS[nombre](argumentos)
    except Exception as e:
        logger.error(f"Error ejecutando herramienta '{nombre}': {e}")
        return {"exito": False, "error": str(e)}
