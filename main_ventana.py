"""Arranque del programa: ``python main_ventana.py``.

Esta es **la única** forma de arrancar. Antes había tres (la consola, la ventana
de menús y esta) y se elegía una al arrancar; ahora no hay nada que elegir.

La vista es ``VentanaAjedrez`` y **no** cumple ``InterfazVista``: no tiene
menús. En lugar de preguntar, la pantalla llama directamente a los métodos del
controlador cuando alguien pulsa un botón o hace clic en una casilla
(``aplicar_jugada``, ``guardar``, ``cargar``, ``deshacer``, etc.). El controlador
ya estaba preparado: lo único que hizo falta fue ``aplicar_jugada(texto)`` para
que no tuviera que pasar por ``pedir_jugada()``.

Por eso no hay ningún puente de hilos. Todo corre en el hilo principal de
``tkinter``, y eso es lo correcto: un clic llama a un método, ese método actualiza
la partida y la ventana se redibuja. No hay esperas entre hilos, no hay eventos
cruzados y no hay nada que sincronizar. El bucle es el de siempre:
``root.mainloop()``.

El almacenamiento se decide aquí y sin preguntar: **JSON**. Antes se ofrecían
JSON y FEN con un diálogo al arrancar, y con la consola y la ventana de menús
fuera ya no hay a quién darle la elección. Se queda el JSON, que es el formato por
defecto del programa y el único que guarda el historial (y por tanto el único que
permite deshacer). ``FENStorage`` y ``storage/fen_storage.py`` **se conservan**,
con sus pruebas: siguen siendo la forma de exportar una posición a otro
programa, aunque la ventana ya no los ofrezca.
"""

from __future__ import annotations

import sys
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from storage.json_storage import JSONStorage  # noqa: E402
from views.ventana import VentanaAjedrez  # noqa: E402

# Carpeta donde se guardan las partidas. Se resuelve a partir de la ubicación de
# este archivo, y no del directorio desde el que se ejecute, para que las
# partidas se guarden siempre en el mismo sitio.
CARPETA_DATOS = RAIZ / "data"


def main() -> int:
    root = tk.Tk()
    root.withdraw()

    # Se construye la ventana del tablero primero y se le pasa un
    # almacenamiento provisional, que se sustituye justo después. Se hace en este
    # orden porque ``VentanaAjedrez`` necesita un almacenamiento en el
    # constructor, y porque así la ventana ya está construida cuando se
    # configura el definitivo.
    ventana = VentanaAjedrez(root)
    root.deiconify()
    root.update()

    try:
        storage = JSONStorage(CARPETA_DATOS / "partidas.json")
    except OSError as error:
        # Si la carpeta de datos no se puede crear no hay nada que hacer: avisar
        # y terminar es mejor que dejar una traza de error. Se cierra ``root``
        # antes de volver, o el proceso se queda con una ventana muerta.
        messagebox.showerror(
            "Error", f"No se pudo preparar la carpeta de datos ({error})", parent=root
        )
        root.destroy()
        return 1

    ventana.storage = storage
    ventana.controlador.storage = storage
    ventana._anotar(f"Las partidas se guardarán en: {storage.ruta}")

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
