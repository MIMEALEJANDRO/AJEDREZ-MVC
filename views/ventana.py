"""La ventana jugable: la clase que junta construcción, dibujo y eventos.

Este módulo es **el punto de entrada** de la pantalla. ``VentanaAjedrez`` es un
único objeto de ``tkinter`` formado por tres mezclas, una por cada cosa que hace:

* ``views.ventana_widgets.WidgetsVentana`` — construye el árbol de widgets y
  sabe mostrar y ocultar el panel de FEN. Aquí también está la configuración
  (tamaños, colores) y el **bando por defecto**.
* ``views.ventana_dibujo.DibujoVentana`` — pinta el tablero y refresca los
  paneles.
* ``views.ventana_eventos.EventosVentana`` — reacciona a los clics y a los
  botones.

Por qué mezclas y no tres clases que colaboren: son **un solo objeto**. Tkinter
monta un árbol de widgets y las tres mitades lo comparten entero (el lienzo, la
etiqueta del turno, el panel de FEN). Con composición habría que ir pasando la
ventana por todas partes y habría un `ventana.lienzo` al que dejar de poder
acceder. Con mezclas el objeto sigue siendo uno, ``ventana.atributo`` sigue
funcionando igual y **las pruebas y el guion de humo no se tocan**.

El reparto está en el README, y también en el docstring de cada uno de los tres
módulos.

Lo que esta ventana **no** hace, y es deliberado:

* No implementa ``views.interfaz.InterfazVista``, y no tiene que hacerlo: no
  tiene menús. La pantalla *tira* de las acciones del controlador en vez de que
  el controlador empuje menús. Quien **sí** cumple el contrato es
  ``SalidaDeConsola``, el adaptador de abajo, que es lo que el controlador recibe
  como ``vista``.
* No sabe ninguna regla de ajedrez. Si una jugada es legal lo decide el
  controlador, que a su vez se lo pregunta al modelo.
* No decide quién puede mover. Lo decide
  ``PartidaController.color_que_juega``.

``SalidaDeConsola`` (abajo) es el puente con el controlador: le da los cuatro
métodos que el controlador invoca de verdad sin tener que implementar el
``Protocol`` entero.
"""

from __future__ import annotations

import tkinter as tk

from controllers.partida_controller import PartidaController
from models.enums import Color
from storage.base_storage import BaseStorage
from views.interfaz import texto_del_error
from views.ventana_dibujo import DibujoVentana
from views.ventana_eventos import EventosVentana
from views.ventana_widgets import WidgetsVentana

# Se reexportan las constantes que usan otros modulos y las pruebas, para que
# ``from views.ventana import LADO_CASILLA`` siga funcionando. Viven en el
# modulo de construccion, que es donde tiene sentido que esten.
from views.ventana_widgets import (  # noqa: F401
    BANDO_POR_DEFECTO,
    CLAVE_BANDO,
    CLARA,
    DESTINO_ACTIVO,
    DESTINO_INACTIVO,
    FONDO,
    INVERSO_BANDO,
    JAQUE,
    LADO_CASILLA,
    LETRA_DE_PROMOCION,
    MARGEN,
    OSCURA,
    SELECCION,
    TEXTO,
    ULTIMA,
)


class SalidaDeConsola:
    """Lo mínimo que el controlador necesita para poder hablar con la ventana.

    El controlador fue escrito contando con que su vista sabe *preguntar*, y por
    eso llama a ``self.vista.mostrar_mensaje(...)`` por todas partes. Esta clase
    le da justo eso.

    **Esta clase es la que cumple ``views.interfaz.InterfazVista``**, entero: los
    seis métodos del contrato son exactamente los que el controlador le invoca de
    verdad por el camino que usa esta ventana. Antes el contrato declaraba
    diecisiete métodos, con los menús de la consola, y esta clase no cumplía ni
    uno; el contrato se redujo a la verdad y ahora ``isinstance`` da ``True``.
    Está comprobado en ``tests/test_ventana.py``.

    ``pedir_confirmacion`` sí es una pregunta de verdad, y se resuelve con un
    ``askyesno``. No es una contradicción: pregunta es "sí o no" y se contesta en
    un segundo, no "elige una de estas ocho opciones y el juego se queda parado".
    El tipo de pregunta que hay que quitar de aquí es el menú, no la confirmación.

    ``elegir_color`` no pregunta nada: devuelve el color que ya esté marcado en
    el panel lateral. También es deliberado. En la consola el color se pregunta
    porque es una decisión que se toma una vez al empezar; en una ventana hay un
    selector siempre visible, y volver a preguntar sería abrir un diálogo para
    preguntar algo que ya se está viendo en pantalla.
    """

    def __init__(self, ventana: "VentanaAjedrez") -> None:
        self.ventana = ventana

    def mostrar_mensaje(self, mensaje: str) -> None:
        self.ventana._anotar(mensaje)

    def mostrar_error(self, error: Exception | str) -> None:
        self.ventana._anotar(texto_del_error(error), error=True)

    def escribir(self, texto: str = "") -> None:
        if texto:
            self.ventana._anotar(texto)

    def titulo(self, texto: str) -> None:
        self.ventana._anotar(texto)

    def pedir_confirmacion(self, pregunta: str) -> bool:
        return bool(messagebox.askyesno("Confirmar", pregunta, parent=self.ventana.root))

    def elegir_color(self) -> Color | None:
        return self.ventana.color


class VentanaAjedrez(WidgetsVentana, DibujoVentana, EventosVentana):
    def __init__(
        self,
        root: tk.Tk,
        storage: BaseStorage | None = None,
        controlador: PartidaController | None = None,
    ) -> None:
        self.root = root
        self.storage = storage
        if controlador is None:
            self.controlador = PartidaController(vista=SalidaDeConsola(self), storage=storage)
        else:
            controlador.vista = SalidaDeConsola(self)
            self.controlador = controlador

        # Casilla seleccionada y a dónde puede ir desde ella. Se guardan aquí
        # porque son el estado de la *interacción*, no el de la partida: no van
        # al historial, no se guardan y no se deshacen.
        self.origen: Posicion | None = None
        self.destinos: list[Movimiento] = []
        # Color con el que se juega. Sale de ``BANDO_POR_DEFECTO`` (la línea que
        # lo decide, arriba en este módulo) y no de un literal suelto, para que
        # cambiarla sea tocar un sitio y no dos.
        self.color: Color | None = BANDO_POR_DEFECTO
        self.girada = False
        # El turno inicial es siempre el de las blancas, así que el bando y el
        # turno no se pueden descuadrar por mucho que se cambie el selector: por
        # eso basta con poner de acuerdo el bando con el controlador.
        self.controlador.nueva_partida(self.color)

        self._construir()
        self._refrescar()
