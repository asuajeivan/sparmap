# SPARMAP — Agente WhatsApp con IA

## Estado actual: EN DESARROLLO

---

## Completado

### 1. Estructura del proyecto
- [x] Repositorio Git inicializado
- [x] Estructura de carpetas: agent/, config/, knowledge/, tests/
- [x] requirements.txt con dependencias (FastAPI, Anthropic, httpx, SQLAlchemy, etc.)
- [x] Dockerfile y docker-compose.yml
- [x] .env.example con todas las variables necesarias
- [x] .gitignore configurado

### 2. Configuracion del negocio
- [x] config/business.yaml — datos de SPARMAP (direccion, telefono, horario, servicios)
- [x] config/prompts.yaml — system prompt del agente
- [x] Direccion: Local 05, C.C Rosita, entre Av 39 y 40, C. 31, Acarigua 3301, Portuguesa
- [x] Telefono humano: 0412-0402832
- [x] Email: Sparmap.llanos@gmail.com
- [x] Horario tienda: Lun-Vie 8am-5pm, Sab 8am-12pm, Dom cerrado

### 3. Agente de IA
- [x] agent/brain.py — cerebro basico (sin Odoo)
- [x] agent/brain_odoo.py — cerebro con tool_use para consultar Odoo en tiempo real
- [x] agent/memory.py — memoria de conversaciones (SQLite/PostgreSQL)
- [x] agent/main.py — servidor FastAPI con webhook de WhatsApp
- [x] agent/tools.py — funciones auxiliares

### 4. Integracion Odoo v17
- [x] agent/odoo/conector.py — cliente XML-RPC compatible con Odoo v14-v18
- [x] agent/odoo/herramientas.py — herramientas de negocio
- [x] Conexion verificada — Odoo 17.0+e, uid=12
- [x] 3,562 productos en inventario, 1,878 con stock
- [x] 149 categorias (mayoría bajo ELECTRICIDAD/)
- [x] Filtro de categorias contables/administrativas (ACTIVO, COSTOS, GASTOS, PASIVO, etc.)
- [x] Agrupacion por subcategoria en catalogo (ultimo nivel)
- [x] Credenciales de Odoo configuradas en .env

### 5. Herramientas del agente (tool_use)
- [x] buscar_producto(nombre) — busca en product.product por nombre, retorna disponibilidad y precio
- [x] obtener_catalogo(categoria?) — lista productos disponibles agrupados por subcategoria, con precio

### 6. Reglas del agente
- [x] Sin nombre — respuestas neutrales y directas
- [x] Disponible 24/7 (el horario es solo de la tienda fisica)
- [x] Da precios (list_price de Odoo)
- [x] NO dice cuantas unidades hay en stock (solo disponible/no disponible)
- [x] NO da cotizaciones formales — deriva al 0412-0402832
- [x] NO agenda servicios — deriva al 0412-0402832
- [x] Deriva a humano con numero 0412-0402832 cuando no puede resolver
- [x] Excluye categorias contables del catalogo

### 7. Proveedores de WhatsApp
- [x] agent/providers/base.py — interfaz comun
- [x] agent/providers/__init__.py — factory de proveedores
- [x] agent/providers/whapi.py — adaptador Whapi.cloud (recomendado)
- [x] agent/providers/meta.py — adaptador Meta Cloud API
- [x] agent/providers/twilio.py — adaptador Twilio

### 8. Documentacion tecnica
- [x] Modelo entidad-relacion Odoo v17 documentado (memory/odoo-modelo-datos.md)
- [x] Diferencias v17 vs v18 documentadas para futura migracion
- [x] Campos reales extraidos del codigo fuente de Odoo

---

## Pendiente

### 9. API key de Anthropic
- [ ] Configurar ANTHROPIC_API_KEY en .env
- [ ] Verificar conexion con Claude API

### 10. Test local del agente
- [ ] Ejecutar python tests/test_local.py
- [ ] Probar consulta de producto ("tienen cable 12?")
- [ ] Probar catalogo ("mandame el catalogo")
- [ ] Probar derivacion a humano ("quiero una cotizacion")
- [ ] Probar direccion y horario ("donde quedan?")
- [ ] Ajustar prompts si las respuestas no son las esperadas

### 11. Proveedor de WhatsApp (Whapi.cloud)
- [ ] Crear cuenta en whapi.cloud
- [ ] Vincular numero de WhatsApp (escanear QR)
- [ ] Obtener WHAPI_TOKEN
- [ ] Configurar WHAPI_TOKEN en .env
- [ ] Configurar webhook URL en panel de Whapi

### 12. Deploy
- [ ] Elegir plataforma (Railway, Render, VPS)
- [ ] Configurar variables de entorno en produccion
- [ ] Deploy del contenedor Docker
- [ ] Configurar URL del webhook en Whapi con la URL publica
- [ ] Migrar base de datos a PostgreSQL (produccion)
- [ ] Verificar que el webhook recibe mensajes
- [ ] Prueba end-to-end: enviar mensaje real por WhatsApp

### 13. Post-deploy
- [ ] Monitoreo de logs
- [ ] Ajustes de prompts segun feedback real
- [ ] Configurar dominio personalizado (opcional)
- [ ] Backup de base de datos

---

## Decisiones tecnicas

| Tema | Decision |
|---|---|
| Motor IA | Claude Sonnet 4.6 (Anthropic API) |
| Proveedor WhatsApp | Whapi.cloud (recomendado) |
| ERP / Inventario | Odoo v17 via XML-RPC |
| Base de datos agente | SQLite (dev) / PostgreSQL (prod) |
| Framework web | FastAPI + uvicorn |
| Deploy | Por definir |

## Datos de la instancia Odoo

| Dato | Valor |
|---|---|
| Version | 17.0+e-20240730 |
| URL | https://sparmap.com.ve/ |
| DB | sparmap.com.ve |
| Usuario | rsanchez@sparmap.com.ve |
| Productos totales | 3,562 |
| Productos con stock | 1,878 |
| Categorias | 149 (mayoria bajo ELECTRICIDAD/) |
