# tests/test_local.py — Simulador de chat en terminal

import asyncio
import sys
import os

# Forzar UTF-8 en la salida de la terminal (Windows cp1252 no soporta emojis)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stdin.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agent.memory import inicializar_db, guardar_mensaje, obtener_historial, limpiar_historial

# Usar brain_odoo si Odoo esta activado
ODOO_ENABLED = os.getenv("ODOO_ENABLED", "false").lower() == "true"
if ODOO_ENABLED:
    from agent.brain_odoo import generar_respuesta
else:
    from agent.brain import generar_respuesta

TELEFONO_TEST = "test-local-001"


async def main():
    await inicializar_db()

    # Inicializar Odoo si esta activado
    if ODOO_ENABLED:
        from agent.odoo.conector import ConectorOdoo
        from agent.odoo.herramientas import inicializar as inicializar_odoo
        conector = ConectorOdoo()
        if conector.conectar():
            inicializar_odoo(conector)
            print("  Odoo conectado")
        else:
            print("  ADVERTENCIA: Odoo no pudo conectar")

    print()
    print("=" * 55)
    print("   SPARMAP — Test Local")
    print("=" * 55)
    print()
    print("  Escribe como si fueras un cliente.")
    print("  Comandos: 'limpiar' | 'salir'")
    print()
    print("-" * 55)
    print()

    while True:
        try:
            mensaje = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nTest finalizado.")
            break

        if not mensaje:
            continue

        if mensaje.lower() == "salir":
            print("\nTest finalizado.")
            break

        if mensaje.lower() == "limpiar":
            await limpiar_historial(TELEFONO_TEST)
            print("[Historial borrado]\n")
            continue

        historial = await obtener_historial(TELEFONO_TEST)

        print("\nAgente: ", end="", flush=True)
        respuesta = await generar_respuesta(mensaje, historial, telefono=TELEFONO_TEST)
        print(respuesta)
        print()

        await guardar_mensaje(TELEFONO_TEST, "user", mensaje)
        await guardar_mensaje(TELEFONO_TEST, "assistant", respuesta)


if __name__ == "__main__":
    asyncio.run(main())
