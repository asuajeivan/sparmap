# agent/odoo/conector.py — Cliente XML-RPC para Odoo
# Generado por AgentKit

"""
Conexión con la API oficial de Odoo via XML-RPC.
Compatible con Odoo v14, v15, v16, v17 y v18.

Requiere en .env:
    ODOO_URL=https://tu-empresa.odoo.com
    ODOO_DB=nombre_base_de_datos
    ODOO_USERNAME=usuario_api@empresa.com
    ODOO_API_KEY=tu_api_key_de_odoo

El usuario de Odoo debe tener permisos mínimos:
    - Ventas: Leer (para productos y pedidos)
    - Inventario: Leer (para stock)
    - CRM: Crear/Leer (para leads)
    - Contabilidad: Leer (para facturas — opcional)
"""

import os
import xmlrpc.client
import logging
from functools import cached_property

logger = logging.getLogger("agentkit")


class ConectorOdoo:
    """
    Cliente reutilizable para la API XML-RPC de Odoo.
    La conexión es lazy — solo se autentica cuando se hace la primera llamada.
    """

    def __init__(
        self,
        url: str = None,
        db: str = None,
        username: str = None,
        api_key: str = None,
    ):
        self.url = (url or os.getenv("ODOO_URL", "")).rstrip("/")
        self.db = db or os.getenv("ODOO_DB", "")
        self.username = username or os.getenv("ODOO_USERNAME", "")
        self.api_key = api_key or os.getenv("ODOO_API_KEY", "")
        self._uid: int | None = None

    # ─── Conexión y autenticación ─────────────────────────────────────────────

    @cached_property
    def _common(self):
        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")

    @cached_property
    def _models(self):
        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def conectar(self) -> bool:
        """
        Autentica con Odoo. Retorna True si fue exitoso.
        Llama esto al iniciar el servidor para verificar credenciales.
        """
        if self._uid:
            return True
        if not all([self.url, self.db, self.username, self.api_key]):
            logger.warning("Credenciales de Odoo incompletas — integración desactivada")
            return False
        try:
            uid = self._common.authenticate(self.db, self.username, self.api_key, {})
            if not uid:
                logger.error("Autenticación Odoo fallida — verificar usuario y API key")
                return False
            self._uid = uid
            version = self._common.version()
            logger.info(
                f"Conectado a Odoo {version.get('server_version', '?')} "
                f"en {self.url} como uid={uid}"
            )
            return True
        except Exception as e:
            logger.error(f"Error conectando con Odoo: {e}")
            return False

    def esta_disponible(self) -> bool:
        """Retorna True si la integración está configurada y autenticada."""
        if not self._uid:
            self.conectar()
        return bool(self._uid)

    # ─── Operación base ──────────────────────────────────────────────────────

    def llamar(self, modelo: str, metodo: str, args: list, kwargs: dict = None) -> any:
        """
        Ejecuta cualquier operación en la API de Odoo.

        Args:
            modelo:  Nombre del modelo Odoo (ej: "product.product")
            metodo:  Método a ejecutar (ej: "search_read", "create", "write")
            args:    Argumentos posicionales (dominio de búsqueda, IDs, etc.)
            kwargs:  Argumentos con nombre (fields, limit, order, etc.)

        Returns:
            El resultado de la llamada, o None si hubo error.
        """
        if not self.esta_disponible():
            return None
        try:
            return self._models.execute_kw(
                self.db, self._uid, self.api_key,
                modelo, metodo, args, kwargs or {}
            )
        except xmlrpc.client.Fault as e:
            logger.error(f"Error Odoo [{modelo}.{metodo}]: {e.faultString}")
            return None
        except Exception as e:
            logger.error(f"Error llamando Odoo: {e}")
            return None
