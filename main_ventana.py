"""Arranque de la ventana jugable: ``python main_ventana.py``.

Esta es la tercera forma de arrancar el programa, distinta de ``main.py``
(consola) y ``main_gui.py`` (ventana con menús modales). La diferencia no es
estética: es el modo en el que la pantalla habla con el controlador.

En ``main_gui.py`` la vista cumple ``InterfazVista``, pregunta con diálogos
modales y el controlador se ejecuta en un hilo aparte (``PuenteHilos``), porque
los diálogos esperan y el hilo principal no puede esperar. Ahí el controlador
sigue siendo el que "empuja" los menús.

En esta versión, la vista es ``VentanaAjedrez``: **no cumple el contrato** y no
tiene menús. En lugar de preguntar, llama directamente a los métodos del
controlador cuando alguien pulsa un botón o hace clic en una casilla
(``aplicar_jugada``, ``guardar``, ``cargar``, ``deshacer``, etc.). El controlador
ya estaba preparado: lo único que se añadió fue ``aplicar_jugada(texto)`` para
que no tuviera que pasar por ``pedir_jugada()``.

Por eso no hay ningún puente de hilos aquí. Todo corre en el hilo principal de
tkinter, y eso es lo correcto: un clic llama a un método, ese método actualiza
la partida y la ventana se redibuja. No hay esperas entre hilos, no hay eventos
cruzados y no hay nada que sincronizar. El bucle es el de siempre: ``root.mainloop()``.

El almacenamiento se elige igual que en la consola, por simplicidad: la misma
pregunta, la misma lógica, y al final se pasa a la ventana. Eso mantiene la
posibilidad de elegir entre JSON y FEN sin duplicar código.
"""

from __future__ import annotations

import sys
from pathlib import Path

import tkinter as tk
from tkinter import messagebox
RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from controllers.partida_controller import PartidaController  # noqa: E402
from main import ALMACENAMIENTOS, _ubicacion_de  # noqa: E402
from storage.base_storage import BaseStorage  # noqa: E402
from views.ventana import VentanaAjedrez  # noqa: E402


def elegir_almacenamiento_en_ventana(root: tk.Tk) -> BaseStorage | None:
    """Pregunta el formato de guardado con un diálogo modal.

    Reutiliza ``ALMACENAMIENTOS`` de ``main.py`` para no duplicar las opciones: el
    menú es el mismo, solo cambia la forma de preguntarlo.

    Se recibe la ventana principal **ya visible** a propósito, y no una
    ``Tk()`` oculta. Un ``Toplevel`` cuyo padre está retirado con ``withdraw()``
    no llega a mostrarse nunca, y el programa se queda esperando a un ``Enter``
    que no aparece en ninguna parte: parece que no arranca, cuando lo cierto es
    que la pregunta ya está en pantalla en algún sitio que no se ve. Montar el
    diálogo encima de la ventana real evita ese caso por completo.
    """
    ventana = tk.Toplevel(root)
    ventana.title("Formato de guardado")
    ventana.transient(root)
    ventana.resizable(False, False)
    ventana.grab_set()

    marco = tk.Frame(ventana, padx=20, pady=20)
    marco.grid()

    tk.Label(marco, text="¿En qué formato se guardarán las partidas?").grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )

    eleccion: dict[str, str | None] = {"clave": "1"}

    seleccion = tk.StringVar(marco, value="1")
    for indice, (clave, (descripcion, _)) in enumerate(ALMACENAMIENTOS.items()):
        tk.Radiobutton(
            marco, text=f"{clave}. {descripcion}", value=clave, variable=seleccion,
        ).grid(row=1 + indice, column=0, columnspan=2, sticky="w")

    def cerrar(clave: str | None) -> None:
        eleccion["clave"] = clave
        ventana.destroy()

    def aceptar() -> None:
        cerrar(seleccion.get())

    botones = tk.Frame(marco)
    botones.grid(row=1 + len(ALMACENAMIENTOS), column=0, columnspan=2, sticky="e", pady=(12, 0))
    tk.Button(botones, text="Aceptar", command=aceptar).grid(row=0, column=0, padx=(0, 6))
    tk.Button(botones, text="Cancelar", command=lambda: cerrar(None)).grid(row=0, column=1)

    ventana.bind("<Return>", lambda _e: aceptar())
    ventana.bind("<Escape>", lambda _e: cerrar(None))
    ventana.protocol("WM_DELETE_WINDOW", lambda: cerrar(None))

    ventana.wait_window()
    clave = eleccion.get("clave")
    if clave not in ALMACENAMIENTOS:
        return None
    _, constructor = ALMACENAMIENTOS[clave]
    try:
        return constructor()
    except OSError as error:
        messagebox.showerror(
            "Error", f"No se pudo preparar la carpeta de datos ({error})", parent=root
        )
        return None


def main() -> int:
    root = tk.Tk()
    root.withdraw()

    # Se construye la ventana del tablero primero, y se le pasa un
    # almacenamiento provisional. Lo que gana con esto es que ``root`` está
    # visible cuando se plantea la pregunta del formato, que es la condición para
    # que el diálogo aparezca (ver ``elegir_almacenamiento_en_ventana``). La
    # pregunta se hace igualmente antes de jugar, así que el orden en que se ve
    # no cambia.
    ventana = VentanaAjedrez(root)
    root.deiconify()
    root.update()

    storage = elegir_almacenamiento_en_ventana(root)
    if storage is None:
        # Si cancelan la elección no se arranca: es mejor cerrarse que aparecer
        # con un formato por defecto que nadie ha elegido.
        root.destroy()
        return 0

    ventana.storage = storage
    ventana.controlador.storage = storage
    ventana._anotar(f"Las partidas se guardarán en: {_ubicacion_de(storage)}")

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
