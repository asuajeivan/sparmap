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
    Busca productos en el catalogo por nombre (busqueda flexible).
    Divide el termino en palabras y busca con AND para coincidencias parciales.
    Ej: "breaker tripolar" busca productos que tengan "breaker" Y "tripolar" en el nombre.
    Si no encuentra con AND, reintenta con cada palabra por separado (OR).
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    palabras = nombre.strip().split()
    base_domain = [["active", "=", True], ["sale_ok", "=", True]]

    # Primero: buscar con AND (todas las palabras deben coincidir)
    dominio_and = list(base_domain)
    for palabra in palabras:
        dominio_and.append(["name", "ilike", palabra])

    resultados = _odoo.llamar(
        "product.product", "search_read",
        [dominio_and],
        {
            "fields": ["name", "list_price", "qty_available", "default_code", "categ_id"],
            "limit": 15,
            "order": "qty_available desc, name asc",
        }
    )

    # Si no hay resultados con AND y hay mas de una palabra, buscar con OR
    if not resultados and len(palabras) > 1:
        dominio_or = list(base_domain)
        or_conditions = [["name", "ilike", p] for p in palabras]
        # Construir OR con pipes de Odoo
        dominio_or_full = []
        for i, cond in enumerate(or_conditions):
            if i > 0:
                dominio_or_full.insert(0, "|")
            dominio_or_full.append(cond)
        dominio_or = dominio_or_full + base_domain

        resultados = _odoo.llamar(
            "product.product", "search_read",
            [dominio_or],
            {
                "fields": ["name", "list_price", "qty_available", "default_code", "categ_id"],
                "limit": 15,
                "order": "qty_available desc, name asc",
            }
        )

    if resultados is None:
        return {"exito": False, "error": "No se pudo consultar el catalogo."}

    # Solo devolver productos CON stock — los sin stock no existen para el cliente
    productos = [
        {
            "nombre": p["name"],
            "precio": p["list_price"],
            "categoria": p["categ_id"][1] if p.get("categ_id") else "",
        }
        for p in resultados
        if p["qty_available"] > 0
    ]

    if not productos:
        return {"exito": True, "datos": [], "mensaje": f"No tenemos '{nombre}' disponible."}
    return {"exito": True, "datos": productos}


def obtener_catalogo(categoria: str = "") -> dict:
    """
    Retorna todos los productos disponibles (con stock > 0).
    Opcionalmente filtra por categoria.
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    # Solo categorias de productos vendibles (excluir contables/administrativas)
    CATEGORIAS_EXCLUIDAS = [
        "ACTIVO", "COSTOS", "GASTOS", "PASIVO", "INGRESOS", "FLETES", "NO UTILIZAR"
    ]
    dominio = [
        ["active", "=", True],
        ["sale_ok", "=", True],
        ["qty_available", ">", 0],
    ]
    for cat_excl in CATEGORIAS_EXCLUIDAS:
        dominio.append(["categ_id.complete_name", "not ilike", cat_excl])
    if categoria:
        dominio.append(["categ_id.complete_name", "ilike", categoria])

    resultados = _odoo.llamar(
        "product.product", "search_read",
        [dominio],
        {
            "fields": ["name", "list_price", "qty_available", "default_code", "categ_id"],
            "limit": 50,
            "order": "categ_id, name asc",
        }
    )

    if resultados is None:
        return {"exito": False, "error": "No se pudo consultar el catalogo."}
    if not resultados:
        return {"exito": True, "datos": [], "mensaje": "No hay productos disponibles en este momento."}

    # Agrupar por subcategoria (ultimo nivel del nombre completo)
    por_categoria = {}
    # Necesitamos el complete_name de la categoria
    categ_ids = list({p["categ_id"][0] for p in resultados if p.get("categ_id")})
    categ_map = {}
    if categ_ids:
        cats = _odoo.llamar(
            "product.category", "read",
            [categ_ids],
            {"fields": ["complete_name"]}
        )
        if cats:
            categ_map = {c["id"]: c["complete_name"] for c in cats}

    for p in resultados:
        cat_id = p["categ_id"][0] if p.get("categ_id") else 0
        cat_name = categ_map.get(cat_id, p["categ_id"][1] if p.get("categ_id") else "Otros")
        # Usar solo el ultimo nivel para agrupar (ej: "ELECTRICIDAD / CABLES ELECON" -> "CABLES ELECON")
        cat_short = cat_name.split(" / ")[-1] if " / " in cat_name else cat_name
        if cat_short not in por_categoria:
            por_categoria[cat_short] = []
        por_categoria[cat_short].append({
            "nombre": p["name"],
            "precio": p["list_price"],
        })

    return {"exito": True, "datos": por_categoria}


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
            "Busca productos en el inventario por nombre. "
            "Usalo cuando el cliente pregunta si tienen un producto, "
            "disponibilidad, stock, o busca algo especifico (cable 12, breaker, enchufe, etc.)."
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
        "name": "obtener_catalogo",
        "description": (
            "Retorna el catalogo completo de productos disponibles, agrupados por categoria. "
            "Usalo cuando el cliente pide el catalogo, lista de productos, "
            "o quiere ver todo lo que hay disponible. "
            "Opcionalmente filtra por categoria (cables, iluminacion, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "categoria": {
                    "type": "string",
                    "description": "Categoria para filtrar (opcional). Dejar vacio para todo el catalogo."
                }
            },
            "required": []
        }
    },
]


# ─── Mapa de nombre → función para ejecutar desde brain_odoo.py ─────────────

MAPA_HERRAMIENTAS = {
    "buscar_producto": lambda args: buscar_producto(args["nombre"]),
    "obtener_catalogo": lambda args: obtener_catalogo(args.get("categoria", "")),
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
