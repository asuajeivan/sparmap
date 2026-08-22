# agent/tools.py — Herramientas del agente SPARMAP

import os
import yaml
import logging

logger = logging.getLogger("agentkit")


def cargar_inventario() -> dict:
    """Carga el inventario desde knowledge/inventario.yaml."""
    try:
        with open("knowledge/inventario.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("knowledge/inventario.yaml no encontrado")
        return {}


def buscar_producto(consulta: str) -> str:
    """Busca un producto en el inventario por nombre."""
    data = cargar_inventario()
    categorias = data.get("categorias", {})
    consulta_lower = consulta.lower()
    encontrados = []

    for categoria, productos in categorias.items():
        for p in productos:
            if consulta_lower in p.get("nombre", "").lower():
                estado = "Disponible" if p.get("disponible") else "No disponible"
                desc = f" — {p['descripcion']}" if p.get("descripcion") else ""
                encontrados.append(f"{p['nombre']}{desc} [{estado}]")

    if encontrados:
        return "\n".join(encontrados)
    return "No encontre ese producto en el inventario."


def obtener_catalogo() -> str:
    """Retorna el catalogo completo de productos disponibles."""
    data = cargar_inventario()
    categorias = data.get("categorias", {})
    lineas = []

    for categoria, productos in categorias.items():
        nombre_cat = categoria.replace("_", " ").title()
        disponibles = [p for p in productos if p.get("disponible", False)]
        if not disponibles:
            continue
        lineas.append(f"\n*{nombre_cat}*")
        for p in disponibles:
            lineas.append(f"  - {p['nombre']}")

    if lineas:
        return "Productos disponibles:" + "\n".join(lineas)
    return "No hay productos disponibles en este momento."


def obtener_info_tienda() -> dict:
    """Retorna la informacion de contacto y ubicacion."""
    return {
        "direccion": "Local 05, C.C Rosita, entre Av 39 y 40, C. 31, Acarigua 3301, Portuguesa",
        "telefonos_asesores": ["+58 412-0399694", "+58 412-0402832"],
        "email": "Sparmap.llanos@gmail.com",
        "horario": {
            "lunes_viernes": "8:00 a.m. - 5:00 p.m.",
            "sabado": "8:00 a.m. - 12:00 p.m.",
            "domingo": "Cerrado"
        }
    }
