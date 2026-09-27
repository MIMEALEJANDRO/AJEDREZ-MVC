"""Arranque de la versión con ventana: ``python main_gui.py``.

Son unas veinte líneas, y que sean tan pocas es la mejor prueba de que la
arquitectura funciona: la partida, sus reglas y su guardado son exactamente los
mismos que en la consola, y lo único que cambia es quién pinta y quién
pregunta. Si al escribir esta versión hubiera hecho falta tocar el controlador,
significaría que el contrato de la vista no estaba donde debía.

Qué hace aquí y qué hace ``main.py``: casi lo mismo. Los dos eligen formato de
guardado, montan la vista, construyen el controlador con sus colaboradores y lo
arrancan. La diferencia es cómo se ejecuta ``controlador.ejecutar()``, y
depende de si la pantalla puede bloquear:

* ``main.py`` lo llama directamente. En consola, esperar a una tecla no estorba
  a nadie porque el único hilo del programa no tiene nada más que hacer.
* Aquí se llama en un hilo aparte (``PuenteHilos``), porque ``tkinter`` no
  puede dejar su hilo principal esperando: es el que dibuja y el que atiende
  los clics.

Y ese reparto es lo que obliga a que el **orden** de estas tres líneas sea el
que es:

1. El controlador se pone en un hilo aparte.
2. La vista recibe ese puente, para poder encolarle los dibujos.
3. La ventana entra en su bucle de eventos (``mainloop``), que es el único
   hilo que dibuja.

Si la ventana entrara en ``mainloop`` antes de arrancar el puente, el
controlador intentaría pintar antes de que existiera el bucle que atiende los
``after``, y se quedaría esperando para siempre. Por eso ``arrancar()`` va
justo antes de ``mainloop()`` y no antes.
"""

from __future__ import annotations

import sys
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from controllers.partida_controller import PartidaController  # noqa: E402
from main import _ubicacion_de, elegir_almacenamiento  # noqa: E402
from views.hilo import PuenteHilos  # noqa: E402
from views.vista_gui import VistaGUI  # noqa: E402

CARPETA_DATOS = RAIZ / "data"


def main() -> int:
    """Abre la ventana y devuelve el código de salida del proceso.

    Se devuelve el código en vez de llamar a ``sys.exit`` dentro, por lo mismo
    que en ``main.py``: así se puede probar sin cerrar el intérprete.
    """
    root = tk.Tk()
    vista = VistaGUI(root)

    # El formato de guardado se pregunta con la misma función que la consola
    # usa, y funciona porque esa función solo habla con la vista a través del
    # contrato. Es un buen ejemplo de por qué el Protocol compensa: sin él,
    # este menú estaría escrito dos veces.
    storage = elegir_almacenamiento(vista)
    vista.mostrar_mensaje(f"Las partidas se guardarán en: {_ubicacion_de(storage)}")

    controlador = PartidaController(vista=vista, storage=storage)
    puente = PuenteHilos(
        controlador.ejecutar,
        al_terminar=lambda _resultado: root.after(0, root.quit),
        al_fallar=_al_fallar(root),
    )
    # El puente se le pasa a la vista *después* de construirlo y antes de
    # arrancar. A partir de aquí la vista ya sabe que hay otro hilo.
    vista.puente = puente

    vista.mostrar_mensaje("Abriendo la ventana...")
    puente.arrancar()
    root.mainloop()
    return 0


def _al_fallar(root: tk.Tk):
    """Manejador de errores del hilo del controlador.

    Se usa una fábrica y no una función suelta para poder capturar ``root``
    sin pasarlo como argumento en ``main()``, que ya tiene bastante.

    Lo importante es el ``root.after(0, ...)``: el puente avisa desde el hilo
    del controlador, y ese hilo no puede tocar la ventana. ``messagebox`` es
    tkinter, así que también tiene que ejecutarse en el hilo principal. Por eso
    el aviso se *encola* en lugar de mostrarse aquí directamente.
    """

    def manejar(error: BaseException) -> None:
        traceback.print_exception(type(error), error, error.__traceback__)
        root.after(0, _avisar_y_salir, root, error)

    return manejar


def _avisar_y_salir(root: tk.Tk, error: BaseException) -> None:
    """Muestra el error y cierra. Solo se ejecuta en el hilo principal."""
    messagebox.showerror(
        "Error inesperado",
        f"{type(error).__name__}: {error}\n\n"
        "La traza completa se ha escrito en la consola desde la que se "
        "arrancó el programa.",
    )
    root.quit()


if __name__ == "__main__":
    raise SystemExit(main())
