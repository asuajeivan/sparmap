# agent/odoo/herramientas.py — Operaciones de negocio sobre Odoo
# Generado por AgentKit

"""
Todas las acciones que el agente puede ejecutar sobre Odoo.
Cada función retorna un dict con 'exito' (bool) y 'datos' o 'error'.

El agente de IA (brain_odoo.py) llama estas funciones según
lo que el cliente pide por WhatsApp.
"""

import logging
import unicodedata
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


def _quitar_acentos(texto: str) -> str:
    """Quita acentos/tildes de un texto. 'lámpara' → 'lampara'."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


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

    # Normalizar: quitar acentos para buscar ambas variantes
    nombre_limpio = _quitar_acentos(nombre.strip())
    palabras = nombre_limpio.split()
    campos_busqueda = ["name", "list_price", "qty_available", "default_code", "categ_id"]
    opts = {"fields": campos_busqueda, "limit": 20, "order": "qty_available desc, name asc"}
    base_domain = [["active", "=", True], ["sale_ok", "=", True]]

    # Buscar con AND (todas las palabras deben coincidir)
    dominio_and = list(base_domain)
    for palabra in palabras:
        dominio_and.append(["name", "ilike", palabra])

    resultados = _odoo.llamar("product.product", "search_read", [dominio_and], opts)

    # Si no hay resultados y hay mas de una palabra, buscar con OR
    if not resultados and len(palabras) > 1:
        or_conditions = [["name", "ilike", p] for p in palabras]
        dominio_or_full = []
        for i, cond in enumerate(or_conditions):
            if i > 0:
                dominio_or_full.insert(0, "|")
            dominio_or_full.append(cond)
        dominio_or = dominio_or_full + base_domain
        resultados = _odoo.llamar("product.product", "search_read", [dominio_or], opts)

    # Si aun no hay, buscar tambien por categoria (ej: "lampara" podria estar en cat ILUMINACION)
    if not resultados:
        dominio_cat = list(base_domain) + [["categ_id.complete_name", "ilike", nombre_limpio]]
        resultados = _odoo.llamar("product.product", "search_read", [dominio_cat], opts)

    if resultados is None:
        return {"exito": False, "error": "No se pudo consultar el catalogo."}

    # Solo devolver productos CON stock — los sin stock no existen para el cliente
    productos = [
        {
            "id": p["id"],
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


def registrar_cliente_interesado(nombre_contacto: str, telefono: str, interes: str, canal: str = "WhatsApp") -> dict:
    """
    Registra un cliente interesado como contacto en Odoo.
    Úsalo cuando un cliente nuevo pide información o quiere que lo contacten.
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    partner_id = _buscar_o_crear_partner(nombre_contacto, telefono, canal)

    if not partner_id:
        return {"exito": False, "error": "No se pudo registrar el cliente."}

    # Actualizar notas del partner con el interes
    _odoo.llamar("res.partner", "write", [[partner_id], {
        "comment": f"Canal: {canal}\nInterés: {interes}",
    }])

    return {
        "exito": True,
        "datos": {"partner_id": partner_id},
        "mensaje": f"Cliente registrado. El equipo de ventas se comunicará contigo pronto."
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
# VENTAS — PRESUPUESTO AUTOMATICO POR COTIZACION
# ═══════════════════════════════════════════════════════════════

def _buscar_o_crear_partner(nombre: str, telefono: str, canal: str = "WhatsApp") -> int | None:
    """Busca un partner por telefono. Si no existe, lo crea con el canal de origen."""
    if not _odoo or not _odoo.esta_disponible():
        return None
    telefono_limpio = telefono.replace("+", "").replace(" ", "").replace("-", "")
    partners = _odoo.llamar(
        "res.partner", "search_read",
        [["|", ["phone", "like", telefono_limpio[-9:]], ["mobile", "like", telefono_limpio[-9:]]]],
        {"fields": ["id"], "limit": 1},
    )
    if partners:
        return partners[0]["id"]
    # Crear partner nuevo con comentario del canal de origen
    partner_id = _odoo.llamar("res.partner", "create", [{
        "name": nombre,
        "phone": telefono,
        "comment": f"Canal: {canal}",
    }])
    return partner_id


def _obtener_o_crear_utm_source(nombre: str) -> int | None:
    """Busca o crea un utm.source para tracking del canal de origen."""
    if not _odoo or not _odoo.esta_disponible():
        return None
    sources = _odoo.llamar(
        "utm.source", "search_read",
        [[["name", "=", nombre]]],
        {"fields": ["id"], "limit": 1},
    )
    if sources:
        return sources[0]["id"]
    try:
        source_id = _odoo.llamar("utm.source", "create", [{"name": nombre}])
        logger.info(f"UTM source creado: {nombre} (ID={source_id})")
        return source_id
    except Exception as e:
        logger.warning(f"No se pudo crear utm.source '{nombre}': {e}")
        return None


def _crear_presupuesto_venta(
    productos_cotizacion: list[dict],
    total: float,
    cliente_nombre: str = "",
    cliente_telefono: str = "",
    canal: str = "WhatsApp",
):
    """Crea un presupuesto (sale.order en borrador) al generar una cotizacion."""
    if not _odoo or not _odoo.esta_disponible():
        logger.warning("Presupuesto no creado: Odoo no disponible")
        return

    # Buscar o crear partner
    partner_id = None
    if cliente_telefono:
        partner_id = _buscar_o_crear_partner(
            cliente_nombre or "Cliente WhatsApp", cliente_telefono, canal,
        )
        logger.info(f"Presupuesto partner_id: {partner_id}")

    if not partner_id:
        logger.error("No se pudo crear presupuesto: sin partner_id")
        return

    # Armar lineas del pedido
    order_lines = [
        (0, 0, {
            "product_id": p["product_id"],
            "product_uom_qty": p["cantidad"],
            "price_unit": p["precio"],
        })
        for p in productos_cotizacion
    ]

    vals = {
        "partner_id": partner_id,
        "order_line": order_lines,
    }

    # Tracking del canal de origen (utm.source)
    source_id = _obtener_o_crear_utm_source(canal)
    if source_id:
        vals["source_id"] = source_id

    logger.info(f"Creando presupuesto sale.order con {len(order_lines)} lineas, canal={canal}")

    try:
        order_id = _odoo.llamar("sale.order", "create", [vals])
        if order_id:
            # Leer numero asignado
            pedido = _odoo.llamar(
                "sale.order", "read",
                [[order_id]],
                {"fields": ["name", "amount_total"]},
            )
            numero = pedido[0]["name"] if pedido else f"ID-{order_id}"
            logger.info(f"Presupuesto creado: {numero} (ID={order_id}) — canal: {canal}")
        else:
            logger.error("No se pudo crear el presupuesto — create retorno None/False")
    except Exception as e:
        logger.error(f"Error creando presupuesto: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════════════
# COTIZACION PDF
# ═══════════════════════════════════════════════════════════════

def generar_cotizacion(productos: list[dict], cliente_nombre: str = "", cliente_telefono: str = "") -> dict:
    """
    Genera una cotizacion PDF a partir de una lista de productos.

    Args:
        productos: Lista de dicts con: nombre, cantidad (cada uno se busca en Odoo para obtener precio)
        cliente_nombre: Nombre del cliente (opcional)
        cliente_telefono: Telefono del cliente (opcional)

    Returns:
        Dict con exito, ruta del PDF, y resumen de la cotizacion
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    productos_cotizacion = []
    no_encontrados = []

    for item in productos:
        nombre = item.get("nombre", "")
        cantidad = item.get("cantidad", 1)
        product_id = item.get("product_id")

        # Si tenemos product_id, leer directamente de Odoo — 1:1 exacto
        if product_id:
            prod_data = _odoo.llamar(
                "product.product", "read",
                [[product_id]],
                {"fields": ["id", "name", "list_price", "qty_available"]},
            )
            if prod_data and prod_data[0].get("qty_available", 0) > 0:
                prod = prod_data[0]
                productos_cotizacion.append({
                    "product_id": prod["id"],
                    "nombre": prod["name"],
                    "precio": prod["list_price"],
                    "cantidad": cantidad,
                })
                continue
            # Si el producto ya no tiene stock, caer al fuzzy search por nombre

        # Buscar producto en Odoo por nombre (fuzzy search)
        nombre_limpio = _quitar_acentos(nombre.strip())
        # Separar por espacios, "/", "(", ")" y "-" para tokenizar bien
        # Conservar digitos sueltos (ej: "8" en "cable 8 AWG") porque son especificaciones criticas
        import re
        palabras = [p for p in re.split(r'[\s/\(\)\-]+', nombre_limpio) if len(p) > 1 or p.isdigit()]
        campos = ["id", "name", "list_price", "qty_available"]
        opts = {"fields": campos, "limit": 1, "order": "qty_available desc"}
        base_domain = [["active", "=", True], ["sale_ok", "=", True], ["qty_available", ">", 0]]

        # Intento 1: AND (todas las palabras)
        dominio_and = list(base_domain)
        for palabra in palabras:
            dominio_and.append(["name", "ilike", palabra])
        resultados = _odoo.llamar("product.product", "search_read", [dominio_and], opts)

        # Intento 2: OR (cualquier palabra) si AND fallo y hay mas de 1 palabra
        if not resultados and len(palabras) > 1:
            or_conditions = [["name", "ilike", p] for p in palabras]
            dominio_or = []
            for i, cond in enumerate(or_conditions):
                if i > 0:
                    dominio_or.insert(0, "|")
                dominio_or.append(cond)
            dominio_or = dominio_or + base_domain
            resultados = _odoo.llamar("product.product", "search_read", [dominio_or], opts)

        if resultados:
            prod = resultados[0]
            productos_cotizacion.append({
                "product_id": prod["id"],
                "nombre": prod["name"],
                "precio": prod["list_price"],
                "cantidad": cantidad,
            })
        else:
            no_encontrados.append(nombre)

    if not productos_cotizacion:
        return {
            "exito": False,
            "error": "No se encontro ninguno de los productos solicitados.",
            "no_encontrados": no_encontrados,
        }

    # Generar PDF
    from agent.pdf_generator import generar_cotizacion_pdf
    ruta_pdf = generar_cotizacion_pdf(
        productos=productos_cotizacion,
        cliente_nombre=cliente_nombre or "Cliente WhatsApp",
        cliente_telefono=cliente_telefono,
    )

    total = sum(p["precio"] * p["cantidad"] for p in productos_cotizacion)

    # Crear presupuesto en modulo de Ventas (sale.order en borrador)
    _crear_presupuesto_venta(
        productos_cotizacion=productos_cotizacion,
        total=total,
        cliente_nombre=cliente_nombre,
        cliente_telefono=cliente_telefono,
        canal="WhatsApp",
    )

    resultado = {
        "exito": True,
        "ruta_pdf": ruta_pdf,
        "productos_cotizados": [
            {"nombre": p["nombre"], "precio": p["precio"], "cantidad": p["cantidad"],
             "subtotal": p["precio"] * p["cantidad"]}
            for p in productos_cotizacion
        ],
        "total": total,
        "mensaje": f"Cotización generada con {len(productos_cotizacion)} productos por ${total:,.2f}.",
    }
    if no_encontrados:
        resultado["no_encontrados"] = no_encontrados
        resultado["mensaje"] += f" No se encontraron: {', '.join(no_encontrados)}."

    return resultado


# ═══════════════════════════════════════════════════════════════
# REPORTE DIARIO (datos desde Odoo)
# ═══════════════════════════════════════════════════════════════

def obtener_datos_reporte_diario() -> dict:
    """
    Recopila todos los datos de Odoo necesarios para el reporte diario.
    Retorna un dict listo para pasar a generar_reporte_diario_pdf().
    """
    if not _odoo or not _odoo.esta_disponible():
        return _sin_odoo()

    from datetime import date, timedelta
    hoy = date.today()
    hace_30 = hoy - timedelta(days=30)

    datos = {}

    # ── Resumen de ventas del dia ─────────────────────────────────
    pedidos_hoy = _odoo.llamar(
        "sale.order", "search_read",
        [[
            ["date_order", ">=", str(hoy)],
            ["state", "in", ["sale", "done"]],
        ]],
        {"fields": ["amount_total"], "limit": 0}
    ) or []

    pedidos_pendientes = _odoo.llamar(
        "sale.order", "search_count",
        [[["state", "in", ["draft", "sent"]]]],
    ) or 0

    datos["resumen_ventas"] = {
        "total_hoy": sum(p["amount_total"] for p in pedidos_hoy),
        "cantidad_pedidos": len(pedidos_hoy),
        "pedidos_pendientes": pedidos_pendientes,
    }

    # ── Cuentas por cobrar ────────────────────────────────────────
    facturas_clientes = _odoo.llamar(
        "account.move", "search_read",
        [[
            ["move_type", "=", "out_invoice"],
            ["payment_state", "in", ["not_paid", "partial"]],
            ["state", "=", "posted"],
        ]],
        {
            "fields": ["partner_id", "name", "amount_residual", "invoice_date_due", "payment_state"],
            "order": "invoice_date_due asc",
            "limit": 30,
        }
    ) or []

    estados_pago = {"not_paid": "Sin pagar", "partial": "Pago parcial"}
    datos["cuentas_por_cobrar"] = [
        {
            "cliente": f["partner_id"][1] if f.get("partner_id") else "—",
            "factura": f["name"],
            "monto": f["amount_residual"],
            "vencimiento": str(f["invoice_date_due"]) if f.get("invoice_date_due") else "—",
            "estado": estados_pago.get(f["payment_state"], f["payment_state"]),
        }
        for f in facturas_clientes
    ]

    # ── Cuentas por pagar ─────────────────────────────────────────
    facturas_proveedores = _odoo.llamar(
        "account.move", "search_read",
        [[
            ["move_type", "=", "in_invoice"],
            ["payment_state", "in", ["not_paid", "partial"]],
            ["state", "=", "posted"],
        ]],
        {
            "fields": ["partner_id", "name", "amount_residual", "invoice_date_due"],
            "order": "invoice_date_due asc",
            "limit": 30,
        }
    ) or []

    datos["cuentas_por_pagar"] = [
        {
            "proveedor": f["partner_id"][1] if f.get("partner_id") else "—",
            "factura": f["name"],
            "monto": f["amount_residual"],
            "vencimiento": str(f["invoice_date_due"]) if f.get("invoice_date_due") else "—",
        }
        for f in facturas_proveedores
    ]

    # ── Stock bajo ────────────────────────────────────────────────
    # Productos almacenables con stock <= reorder min o <= 5 unidades
    productos_stock = _odoo.llamar(
        "product.product", "search_read",
        [[
            ["active", "=", True],
            ["detailed_type", "=", "product"],
            ["qty_available", "<=", 5],
            ["qty_available", ">=", 0],
            ["sale_ok", "=", True],
        ]],
        {
            "fields": ["name", "qty_available", "categ_id"],
            "order": "qty_available asc",
            "limit": 30,
        }
    ) or []

    datos["stock_bajo"] = [
        {
            "producto": p["name"],
            "cantidad": p["qty_available"],
            "minimo": 5,
            "categoria": p["categ_id"][1] if p.get("categ_id") else "—",
        }
        for p in productos_stock
    ]

    # ── Top productos vendidos (ultimos 30 dias) ──────────────────
    lineas_venta = _odoo.llamar(
        "sale.order.line", "search_read",
        [[
            ["order_id.state", "in", ["sale", "done"]],
            ["order_id.date_order", ">=", str(hace_30)],
        ]],
        {
            "fields": ["product_id", "product_uom_qty", "price_subtotal"],
            "limit": 200,
            "order": "price_subtotal desc",
        }
    ) or []

    # Agrupar por producto
    top_map = {}
    for l in lineas_venta:
        pid = l["product_id"][0] if l.get("product_id") else 0
        pname = l["product_id"][1] if l.get("product_id") else "—"
        if pid not in top_map:
            top_map[pid] = {"producto": pname, "cantidad_vendida": 0, "ingresos": 0}
        top_map[pid]["cantidad_vendida"] += l["product_uom_qty"]
        top_map[pid]["ingresos"] += l["price_subtotal"]

    datos["top_productos"] = sorted(
        top_map.values(), key=lambda x: x["ingresos"], reverse=True
    )[:10]

    # ── Proveedores con facturas pendientes ───────────────────────
    prov_map = {}
    for f in facturas_proveedores:
        pname = f["partner_id"][1] if f.get("partner_id") else "—"
        if pname not in prov_map:
            prov_map[pname] = {"proveedor": pname, "facturas_pendientes": 0, "monto_total": 0}
        prov_map[pname]["facturas_pendientes"] += 1
        prov_map[pname]["monto_total"] += f["amount_residual"]

    datos["proveedores_activos"] = sorted(
        prov_map.values(), key=lambda x: x["monto_total"], reverse=True
    )

    return {"exito": True, "datos": datos}


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
    {
        "name": "generar_cotizacion",
        "description": (
            "Genera una cotización en PDF con los productos que el cliente solicita. "
            "IMPORTANTE: NO uses esta herramienta inmediatamente. Primero confirma con el cliente "
            "la lista de productos y cantidades. SOLO úsala después de que el cliente confirme. "
            "CRITICO: SIEMPRE incluye el product_id EXACTO de cada producto (campo 'id' de buscar_producto). "
            "El product_id determina 1:1 que producto y precio va en el PDF. "
            "Si el cliente eligio productos de distintas busquedas, usa el id de CADA busqueda correspondiente — no los mezcles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "productos": {
                    "type": "array",
                    "description": "Lista de productos con product_id, nombre y cantidad",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {
                                "type": "integer",
                                "description": "ID del producto en Odoo (obtenido de buscar_producto). SIEMPRE incluirlo."
                            },
                            "nombre": {
                                "type": "string",
                                "description": "Nombre del producto (respaldo si no hay product_id)"
                            },
                            "cantidad": {
                                "type": "integer",
                                "description": "Cantidad deseada (default: 1)",
                                "default": 1
                            }
                        },
                        "required": ["product_id", "nombre"]
                    }
                },
                "cliente_nombre": {
                    "type": "string",
                    "description": "Nombre del cliente (si se conoce)"
                },
                "cliente_telefono": {
                    "type": "string",
                    "description": "Telefono del cliente"
                }
            },
            "required": ["productos"]
        }
    },
]


# ─── Mapa de nombre → función para ejecutar desde brain_odoo.py ─────────────

MAPA_HERRAMIENTAS = {
    "buscar_producto": lambda args: buscar_producto(args["nombre"]),
    "obtener_catalogo": lambda args: obtener_catalogo(args.get("categoria", "")),
    "generar_cotizacion": lambda args: generar_cotizacion(
        args["productos"],
        args.get("cliente_nombre", ""),
        args.get("cliente_telefono", ""),
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
