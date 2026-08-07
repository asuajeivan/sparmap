# agent/pdf_generator.py — Generador de PDFs profesionales para SPARMAP
"""
Genera cotizaciones y reportes diarios en PDF con encabezado corporativo.

Usa ReportLab + svglib para renderizar el logo SVG.
"""

import os
import io
import logging
from datetime import datetime, date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image,
    HRFlowable, KeepTogether,
)
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

logger = logging.getLogger("agentkit")

# ─── Constantes de diseño ────────────────────────────────────────────────────

LOGO_PATH = Path(__file__).parent / "assets" / "logo.svg"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

COLOR_PRIMARY = colors.HexColor("#030140")
COLOR_ACCENT = colors.HexColor("#48bd36")
COLOR_LIGHT_BG = colors.HexColor("#f5f5f5")
COLOR_WHITE = colors.white
COLOR_GRAY = colors.HexColor("#666666")
COLOR_LIGHT_GRAY = colors.HexColor("#e0e0e0")
COLOR_RED = colors.HexColor("#dc3545")
COLOR_YELLOW = colors.HexColor("#ffc107")

COMPANY_NAME = "SPARMAP, C.A."
COMPANY_RIF = ""  # Se llena desde Odoo si disponible
COMPANY_ADDRESS = "Local 05, C.C Rosita, entre Av 39 y 40, C. 31, Acarigua 3301, Portuguesa"
COMPANY_PHONE = "0412-0402832"
COMPANY_EMAIL = "Sparmap.llanos@gmail.com"
COMPANY_WEB = "https://sparmap.com.ve/"


def _ensure_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "CompanyName", parent=styles["Heading1"],
        fontSize=18, textColor=COLOR_PRIMARY, spaceAfter=2, leading=22,
    ))
    styles.add(ParagraphStyle(
        "CompanyInfo", parent=styles["Normal"],
        fontSize=8, textColor=COLOR_GRAY, spaceAfter=1, leading=10,
    ))
    styles.add(ParagraphStyle(
        "DocTitle", parent=styles["Heading2"],
        fontSize=14, textColor=COLOR_PRIMARY, alignment=TA_CENTER,
        spaceAfter=12, spaceBefore=8,
    ))
    styles.add(ParagraphStyle(
        "SectionTitle", parent=styles["Heading3"],
        fontSize=11, textColor=COLOR_PRIMARY, spaceBefore=14, spaceAfter=6,
        borderWidth=0, leftIndent=0,
    ))
    styles.add(ParagraphStyle(
        "CellText", parent=styles["Normal"],
        fontSize=9, leading=12,
    ))
    styles.add(ParagraphStyle(
        "CellTextRight", parent=styles["Normal"],
        fontSize=9, leading=12, alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        "HeaderCell", parent=styles["Normal"],
        fontSize=9, leading=12, textColor=COLOR_WHITE, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "HeaderCellRight", parent=styles["Normal"],
        fontSize=9, leading=12, textColor=COLOR_WHITE, fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        "FooterText", parent=styles["Normal"],
        fontSize=7, textColor=COLOR_GRAY, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "MetaLabel", parent=styles["Normal"],
        fontSize=9, textColor=COLOR_GRAY,
    ))
    styles.add(ParagraphStyle(
        "MetaValue", parent=styles["Normal"],
        fontSize=9, textColor=COLOR_PRIMARY, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "TotalLabel", parent=styles["Normal"],
        fontSize=11, textColor=COLOR_PRIMARY, fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        "TotalValue", parent=styles["Normal"],
        fontSize=11, textColor=COLOR_ACCENT, fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        "AlertRed", parent=styles["Normal"],
        fontSize=9, textColor=COLOR_RED, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "AlertYellow", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#856404"), fontName="Helvetica-Bold",
    ))
    return styles


def _build_header(styles):
    """Construye el encabezado con logo + info de empresa."""
    elements = []

    # Logo
    logo_drawing = None
    if LOGO_PATH.exists():
        try:
            logo_drawing = svg2rlg(str(LOGO_PATH))
            if logo_drawing:
                scale = 180 / logo_drawing.width
                logo_drawing.width *= scale
                logo_drawing.height *= scale
                logo_drawing.scale(scale, scale)
        except Exception as e:
            logger.warning(f"No se pudo cargar el logo SVG: {e}")

    # Header table: logo left, company info right
    info_lines = [
        Paragraph(COMPANY_ADDRESS, styles["CompanyInfo"]),
        Paragraph(f"Tel: {COMPANY_PHONE} | Email: {COMPANY_EMAIL}", styles["CompanyInfo"]),
        Paragraph(COMPANY_WEB, styles["CompanyInfo"]),
    ]

    if logo_drawing:
        from reportlab.graphics import renderPDF as rPDF
        from reportlab.platypus.flowables import Flowable

        class DrawingFlowable(Flowable):
            def __init__(self, drawing):
                Flowable.__init__(self)
                self.drawing = drawing
                self.width = drawing.width
                self.height = drawing.height

            def draw(self):
                renderPDF.draw(self.drawing, self.canv, 0, 0)

        logo_flowable = DrawingFlowable(logo_drawing)
        header_data = [[logo_flowable, info_lines]]
    else:
        header_data = [[Paragraph(COMPANY_NAME, styles["CompanyName"]), info_lines]]

    header_table = Table(header_data, colWidths=[220, 280])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(header_table)
    elements.append(HRFlowable(width="100%", thickness=2, color=COLOR_ACCENT, spaceAfter=8))

    return elements


def _build_footer_text():
    return (
        f"{COMPANY_NAME} | {COMPANY_ADDRESS}\n"
        f"Tel: {COMPANY_PHONE} | {COMPANY_EMAIL} | {COMPANY_WEB}\n"
        "Precios sujetos a cambio sin previo aviso. Cotización válida por 3 días hábiles."
    )


# ═══════════════════════════════════════════════════════════════
# COTIZACION
# ═══════════════════════════════════════════════════════════════

def generar_cotizacion_pdf(
    productos: list[dict],
    cliente_nombre: str = "Cliente WhatsApp",
    cliente_telefono: str = "",
    numero_cotizacion: str = None,
) -> str:
    """
    Genera un PDF de cotizacion.

    Args:
        productos: Lista de dicts con keys: nombre, precio, cantidad, (subtotal se calcula)
        cliente_nombre: Nombre del cliente
        cliente_telefono: Telefono del cliente
        numero_cotizacion: Numero de cotizacion (se genera si no se da)

    Returns:
        Ruta absoluta del PDF generado
    """
    _ensure_output_dir()
    styles = _get_styles()

    if not numero_cotizacion:
        numero_cotizacion = f"COT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    filename = f"{numero_cotizacion}.pdf"
    filepath = OUTPUT_DIR / filename

    doc = SimpleDocTemplate(
        str(filepath), pagesize=letter,
        topMargin=30, bottomMargin=50, leftMargin=40, rightMargin=40,
    )

    elements = []

    # Header
    elements.extend(_build_header(styles))

    # Title
    elements.append(Paragraph("COTIZACIÓN", styles["DocTitle"]))

    # Meta info: numero, fecha, cliente
    fecha_str = datetime.now().strftime("%d/%m/%Y %I:%M %p")
    meta_data = [
        [Paragraph("N° Cotización:", styles["MetaLabel"]),
         Paragraph(numero_cotizacion, styles["MetaValue"]),
         Paragraph("Fecha:", styles["MetaLabel"]),
         Paragraph(fecha_str, styles["MetaValue"])],
        [Paragraph("Cliente:", styles["MetaLabel"]),
         Paragraph(cliente_nombre, styles["MetaValue"]),
         Paragraph("Telefono:", styles["MetaLabel"]),
         Paragraph(cliente_telefono or "—", styles["MetaValue"])],
    ]
    meta_table = Table(meta_data, colWidths=[90, 160, 70, 180])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_LIGHT_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 16))

    # Product table
    header_row = [
        Paragraph("#", styles["HeaderCell"]),
        Paragraph("Producto", styles["HeaderCell"]),
        Paragraph("Cant.", styles["HeaderCellRight"]),
        Paragraph("P. Unit. (USD)", styles["HeaderCellRight"]),
        Paragraph("Subtotal (USD)", styles["HeaderCellRight"]),
    ]
    table_data = [header_row]
    total = 0.0

    for i, prod in enumerate(productos, 1):
        cantidad = prod.get("cantidad", 1)
        precio = prod.get("precio", 0)
        subtotal = cantidad * precio
        total += subtotal
        table_data.append([
            Paragraph(str(i), styles["CellText"]),
            Paragraph(prod.get("nombre", "—"), styles["CellText"]),
            Paragraph(str(cantidad), styles["CellTextRight"]),
            Paragraph(f"${precio:,.2f}", styles["CellTextRight"]),
            Paragraph(f"${subtotal:,.2f}", styles["CellTextRight"]),
        ])

    # Total row
    table_data.append([
        "", "", "",
        Paragraph("<b>TOTAL:</b>", styles["TotalLabel"]),
        Paragraph(f"<b>${total:,.2f}</b>", styles["TotalValue"]),
    ])

    prod_table = Table(table_data, colWidths=[30, 230, 50, 95, 95])
    prod_table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        # Body
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [COLOR_WHITE, COLOR_LIGHT_BG]),
        ("GRID", (0, 0), (-1, -2), 0.5, COLOR_LIGHT_GRAY),
        # Total row
        ("LINEABOVE", (3, -1), (-1, -1), 1.5, COLOR_PRIMARY),
        ("TOPPADDING", (0, -1), (-1, -1), 8),
        # General
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -2), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(prod_table)

    # Notes
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LIGHT_GRAY))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        "Precios en USD. Cotización válida por 3 días hábiles. "
        "Para confirmar, comuníquese al 0412-0402832.",
        styles["CompanyInfo"],
    ))
    elements.append(Paragraph(
        "Esta cotización es informativa y no constituye un compromiso de venta. "
        "Para formalizar, contacte a uno de nuestros asesores.",
        styles["CompanyInfo"],
    ))

    doc.build(elements)
    logger.info(f"Cotización generada: {filepath}")
    return str(filepath)


# ═══════════════════════════════════════════════════════════════
# REPORTE DIARIO
# ═══════════════════════════════════════════════════════════════

def generar_reporte_diario_pdf(datos: dict) -> str:
    """
    Genera un reporte diario del negocio en PDF.

    Args:
        datos: Dict con las secciones del reporte:
            - resumen_ventas: {total_hoy, cantidad_pedidos, pedidos_pendientes}
            - cuentas_por_cobrar: [{cliente, factura, monto, vencimiento, estado}]
            - cuentas_por_pagar: [{proveedor, factura, monto, vencimiento}]
            - stock_bajo: [{producto, cantidad, minimo, categoria}]
            - top_productos: [{producto, cantidad_vendida, ingresos}]
            - proveedores_activos: [{proveedor, facturas_pendientes, monto_total}]

    Returns:
        Ruta absoluta del PDF generado
    """
    _ensure_output_dir()
    styles = _get_styles()

    fecha_hoy = date.today()
    filename = f"REPORTE-{fecha_hoy.strftime('%Y%m%d')}.pdf"
    filepath = OUTPUT_DIR / filename

    doc = SimpleDocTemplate(
        str(filepath), pagesize=letter,
        topMargin=30, bottomMargin=50, leftMargin=40, rightMargin=40,
    )

    elements = []

    # Header
    elements.extend(_build_header(styles))

    # Title
    elements.append(Paragraph(
        f"REPORTE DIARIO — {fecha_hoy.strftime('%d/%m/%Y')}",
        styles["DocTitle"],
    ))

    # ── Resumen de ventas ────────────────────────────────────────
    resumen = datos.get("resumen_ventas", {})
    if resumen:
        elements.append(Paragraph("Resumen de Ventas", styles["SectionTitle"]))
        resumen_data = [[
            Paragraph("Ventas del día", styles["HeaderCell"]),
            Paragraph("Pedidos del día", styles["HeaderCell"]),
            Paragraph("Pedidos pendientes", styles["HeaderCell"]),
        ], [
            Paragraph(f"${resumen.get('total_hoy', 0):,.2f}", styles["CellTextRight"]),
            Paragraph(str(resumen.get("cantidad_pedidos", 0)), styles["CellTextRight"]),
            Paragraph(str(resumen.get("pedidos_pendientes", 0)), styles["CellTextRight"]),
        ]]
        t = Table(resumen_data, colWidths=[166, 166, 168])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
            ("BACKGROUND", (0, 1), (-1, 1), COLOR_LIGHT_BG),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 1), (-1, 1), "CENTER"),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 10))

    # ── Cuentas por cobrar ───────────────────────────────────────
    cxc = datos.get("cuentas_por_cobrar", [])
    if cxc:
        total_cxc = sum(item.get("monto", 0) for item in cxc)
        elements.append(Paragraph(
            f"Cuentas por Cobrar — Total: ${total_cxc:,.2f}",
            styles["SectionTitle"],
        ))
        header = [
            Paragraph("Cliente", styles["HeaderCell"]),
            Paragraph("Factura", styles["HeaderCell"]),
            Paragraph("Monto (USD)", styles["HeaderCellRight"]),
            Paragraph("Vencimiento", styles["HeaderCell"]),
            Paragraph("Estado", styles["HeaderCell"]),
        ]
        rows = [header]
        for item in cxc:
            rows.append([
                Paragraph(item.get("cliente", "—"), styles["CellText"]),
                Paragraph(item.get("factura", "—"), styles["CellText"]),
                Paragraph(f"${item.get('monto', 0):,.2f}", styles["CellTextRight"]),
                Paragraph(item.get("vencimiento", "—"), styles["CellText"]),
                Paragraph(item.get("estado", "—"), styles["CellText"]),
            ])
        t = Table(rows, colWidths=[130, 80, 90, 90, 110])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 10))

    # ── Cuentas por pagar ────────────────────────────────────────
    cxp = datos.get("cuentas_por_pagar", [])
    if cxp:
        total_cxp = sum(item.get("monto", 0) for item in cxp)
        elements.append(Paragraph(
            f"Cuentas por Pagar — Total: ${total_cxp:,.2f}",
            styles["SectionTitle"],
        ))
        header = [
            Paragraph("Proveedor", styles["HeaderCell"]),
            Paragraph("Factura", styles["HeaderCell"]),
            Paragraph("Monto (USD)", styles["HeaderCellRight"]),
            Paragraph("Vencimiento", styles["HeaderCell"]),
        ]
        rows = [header]
        for item in cxp:
            rows.append([
                Paragraph(item.get("proveedor", "—"), styles["CellText"]),
                Paragraph(item.get("factura", "—"), styles["CellText"]),
                Paragraph(f"${item.get('monto', 0):,.2f}", styles["CellTextRight"]),
                Paragraph(item.get("vencimiento", "—"), styles["CellText"]),
            ])
        t = Table(rows, colWidths=[170, 110, 110, 110])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 10))

    # ── Stock bajo ───────────────────────────────────────────────
    stock = datos.get("stock_bajo", [])
    if stock:
        elements.append(Paragraph(
            f"Alertas de Stock Bajo ({len(stock)} productos)",
            styles["SectionTitle"],
        ))
        header = [
            Paragraph("Producto", styles["HeaderCell"]),
            Paragraph("Categoría", styles["HeaderCell"]),
            Paragraph("Cant. Actual", styles["HeaderCellRight"]),
            Paragraph("Mínimo", styles["HeaderCellRight"]),
            Paragraph("Alerta", styles["HeaderCell"]),
        ]
        rows = [header]
        for item in stock:
            cant = item.get("cantidad", 0)
            minimo = item.get("minimo", 0)
            if cant <= 0:
                alerta = Paragraph("SIN STOCK", styles["AlertRed"])
            elif cant <= minimo:
                alerta = Paragraph("BAJO", styles["AlertYellow"])
            else:
                alerta = Paragraph("OK", styles["CellText"])
            rows.append([
                Paragraph(item.get("producto", "—"), styles["CellText"]),
                Paragraph(item.get("categoria", "—"), styles["CellText"]),
                Paragraph(str(cant), styles["CellTextRight"]),
                Paragraph(str(minimo), styles["CellTextRight"]),
                alerta,
            ])
        t = Table(rows, colWidths=[170, 120, 70, 60, 80])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 10))

    # ── Top productos vendidos ───────────────────────────────────
    top = datos.get("top_productos", [])
    if top:
        elements.append(Paragraph("Top Productos Vendidos (últimos 30 días)", styles["SectionTitle"]))
        header = [
            Paragraph("#", styles["HeaderCell"]),
            Paragraph("Producto", styles["HeaderCell"]),
            Paragraph("Unidades", styles["HeaderCellRight"]),
            Paragraph("Ingresos (USD)", styles["HeaderCellRight"]),
        ]
        rows = [header]
        for i, item in enumerate(top, 1):
            rows.append([
                Paragraph(str(i), styles["CellText"]),
                Paragraph(item.get("producto", "—"), styles["CellText"]),
                Paragraph(str(item.get("cantidad_vendida", 0)), styles["CellTextRight"]),
                Paragraph(f"${item.get('ingresos', 0):,.2f}", styles["CellTextRight"]),
            ])
        t = Table(rows, colWidths=[30, 270, 80, 120])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 10))

    # ── Proveedores activos ──────────────────────────────────────
    proveedores = datos.get("proveedores_activos", [])
    if proveedores:
        elements.append(Paragraph("Proveedores con Facturas Pendientes", styles["SectionTitle"]))
        header = [
            Paragraph("Proveedor", styles["HeaderCell"]),
            Paragraph("Facturas Pend.", styles["HeaderCellRight"]),
            Paragraph("Monto Total (USD)", styles["HeaderCellRight"]),
        ]
        rows = [header]
        for item in proveedores:
            rows.append([
                Paragraph(item.get("proveedor", "—"), styles["CellText"]),
                Paragraph(str(item.get("facturas_pendientes", 0)), styles["CellTextRight"]),
                Paragraph(f"${item.get('monto_total', 0):,.2f}", styles["CellTextRight"]),
            ])
        t = Table(rows, colWidths=[220, 120, 160])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(t)

    # Footer
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LIGHT_GRAY))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        f"Reporte generado automaticamente el {datetime.now().strftime('%d/%m/%Y a las %I:%M %p')} | {COMPANY_NAME}",
        styles["FooterText"],
    ))

    doc.build(elements)
    logger.info(f"Reporte diario generado: {filepath}")
    return str(filepath)
