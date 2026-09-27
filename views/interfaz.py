"""El contrato de la vista: qué necesita saber el controlador para poder hablar.

Este archivo es la respuesta a una pregunta que aparece en cuanto se escribe el
primer programa: *¿qué necesita exactamente la aplicación para poder mostrar y
pedir cosas?*. La respuesta es una lista de métodos, y esa lista se declara aquí
como un :class:`~typing.Protocol`.

Un ``Protocol`` (disponible desde Python 3.8) describe una interfaz sin obligar
a heredar de nada. Se escribe ``class Vista(Protocol)`` y una clase que tenga
esos métodos **es** una vista, sin que tenga que declararlo. Esa es toda la
ventaja frente a una clase base abstracta: añadir un método a la interfaz no
rompe a las clases que ya existían, y una vista puede además tener los métodos
extra que necesite.

Por qué está en ``views/`` y no en ``controllers/``: el contrato describe lo que
la vista **ofrece**, no lo que el controlador **quiere**. Que lo declare la capa
que lo implementa deja la dependencia en un solo sentido (el controlador conoce
la interfaz; la vista no conoce al controlador).

Y por qué existe, en concreto: hasta ahora el controlador importaba
``PartidaView`` solo para poder escribir el tipo de ``vista`` en el constructor.
Eso obligaba a que la consola estuviera instalada para poder probar el
controlador, y convertía "cambiar la vista" en un cambio que tocaba el
controlador. Con este archivo, el controlador depende de la interfaz y ya no de
la consola.

Uso::

    from views.interfaz import InterfazVista, OPCIONES_INICIO

    def imprimir_todo(vista: InterfazVista, ...): ...
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from models.enums import Color
from models.partida import Partida


# --------------------------------------------------------------------------
# Las opciones de cada menú
# --------------------------------------------------------------------------
# Son *datos*, y por eso no viven dentro de la vista: son lo que el programa
# ofrece, no lo que la pantalla pinta. En una ventana con botones serían las
# etiquetas de los botones, y tenerlas en un solo sitio evita que una pantalla
# se quede con la mitad y la otra con la otra mitad.
#
# La clave es lo que la persona escribe y el valor es lo que se lee. El "0" de
# "volver" no es un accidents: es la convención de que la última opción de
# cualquier menú es siempre salir, y `PartidaView.pedir_opcion` la usa como
# salida por defecto cuando se acaba la entrada.

OPCIONES_INICIO = {
    "1": "Partida nueva",
    "2": "Continuar una partida guardada",
    "3": "Gestionar las partidas guardadas",
    "4": "Ayuda",
    "0": "Salir del programa",
}

OPCIONES_PARTIDA = {
    "1": "Introducir una jugada",
    "2": "Ver el historial",
    "3": "Ver el FEN (para copiarlo a otro programa)",
    "4": "Deshacer la última jugada",
    "5": "Guardar la partida",
    "6": "Guardar y empezar otra",
    "7": "Abandonar la partida",
    "8": "Ayuda",
    "0": "Volver al menú principal (la partida se queda como estaba)",
}

OPCIONES_ARCHIVO = {
    "1": "Guardar la partida actual",
    "2": "Cargar una partida guardada",
    "3": "Ver las partidas guardadas",
    "4": "Borrar una partida guardada",
    "0": "Volver al juego",
}


def texto_del_error(error: Exception | str) -> str:
    """Convierte lo que llega a ``mostrar_error`` en un texto presentable.

    Hay tres casos y se distinguen porque cada uno merece un trato distinto:

    * Un ``ErrorAjedrez`` es siempre un problema con lo que escribió la persona,
      así que se muestra tal cual: ya viene redactado para eso.
    * Una cadena suelta es un mensaje redactado por el controlador (por ejemplo
      "no se pudo escribir en disco"). Se muestra tal cual, sin el adorno de
      "error inesperado", que haría pensar en un fallo del programa cuando no lo
      es.
    * Cualquier otra excepción es inesperada y se muestra su tipo, que es la
      información útil para saber qué está fallando.

    Vive aquí, y no dentro de cada vista, porque es una decisión sobre *qué* se
    le dice a la persona, no sobre cómo se lo enseña. La consola lo imprime y
    una ventana lo pone en una etiqueta: si cada una decidiera por su cuenta,
    un día una diría "Error inesperado" donde la otra no, y esa diferencia sería
    un bug difícil de ver.
    """
    from models.errores import ErrorAjedrez

    if isinstance(error, ErrorAjedrez):
        return f"No se pudo completar la acción: {error}"
    if isinstance(error, str):
        return error
    return f"Error inesperado ({type(error).__name__}): {error}"


# --------------------------------------------------------------------------
# El contrato
# --------------------------------------------------------------------------
# La regla que siguen todos los métodos: la vista **muestra** y **pregunta**, y
# nada más. No decide nada (eso es del controlador), no toca el disco (eso es
# del almacenamiento) y no sabe qué es una regla de ajedrez (recibe una
# ``Partida`` ya montada y la pinta).


@runtime_checkable
class InterfazVista(Protocol):
    """Lo que el controlador necesita de cualquier pantalla.

    Los métodos se pueden clasificar en tres familias:

    **Escribir** (devuelven ``None``, no preguntan nada)
        ``escribir``, ``titulo``, ``mostrar_tablero``, ``mostrar_partidas``,
        ``mostrar_historial``, ``mostrar_fen``, ``mostrar_ayuda``,
        ``mostrar_mensaje``, ``mostrar_error``.

    **Preguntar en un menú cerrado** (devuelven la clave elegida)
        ``menu_inicio``, ``menu_partida``, ``menu_archivo``, ``elegir_color``,
        ``pedir_confirmacion``.

    **Pedir un texto libre** (devuelven lo escrito)
        ``pedir_jugada``, ``pedir_texto_opcional``, ``pedir_texto``.

    La diferencia entre ``pedir_texto`` y ``pedir_texto_opcional`` es la que
    importa para un menú: el primero devuelve el valor por defecto si pulsan
    Enter y nunca devuelve ``None``; el segundo devuelve ``None`` si la persona
    responde "-" o no escribe nada, y ese ``None`` es lo que permite cancelar
    una operación. Sin esa distinción, "no quiero guardar" y "me llamo -"
    serían la misma cosa.
    """

    # -- escribir ------------------------------------------------------
    def escribir(self, texto: str = "") -> None:
        """Escribe una línea."""

    def titulo(self, texto: str) -> None:
        """Escribe un título destacado."""

    def mostrar_tablero(self, partida: Partida) -> None:
        """Pinta el tablero, el turno y el estado de la partida."""

    def mostrar_partidas(self, informes: list[dict]) -> None:
        """Pinta la lista de partidas guardadas, con su clave."""

    def mostrar_historial(self, partida: Partida) -> None:
        """Pinta las jugadas en notación legible."""

    def mostrar_fen(self, partida: Partida) -> None:
        """Pinta el FEN, para poder copiarlo a otro programa."""

    def mostrar_ayuda(self) -> None:
        """Pinta el resumen de cómo se juega."""

    def mostrar_mensaje(self, mensaje: str) -> None:
        """Pinta un mensaje normal."""

    def mostrar_error(self, error: Exception | str) -> None:
        """Pinta un error. Recibe la excepción o su texto ya redactado.

        Acepta las dos cosas a propósito: el controlador captura excepciones del
        dominio (que ya traen el mensaje bueno) y a veces escribe un error
        propio sin excepción detrás (un disco que no se puede escribir). Que la
        vista no tenga que distinguir los dos casos simplifica las dos.
        """

    # -- preguntar en un menú -------------------------------------------
    def menu_inicio(self) -> str:
        """Menú principal, antes de empezar a jugar. Devuelve la clave."""

    def menu_partida(self) -> str:
        """Menú de la partida en curso. Devuelve la clave."""

    def menu_archivo(self) -> str:
        """Menú de gestión de partidas guardadas. Devuelve la clave."""

    def elegir_color(self) -> Color:
        """Pregunta con qué color se juega."""

    def pedir_confirmacion(self, pregunta: str) -> bool:
        """Sí o no. ``False`` también si no hay quien responda."""

    # -- pedir un texto libre -------------------------------------------
    def pedir_jugada(self) -> str:
        """Pide una jugada escrita. Vacía si no se escribe nada."""

    def pedir_texto_opcional(self, pregunta: str) -> str | None:
        """Pide un texto donde ``None`` significa "he cancelado"."""

    def pedir_texto(self, pregunta: str, por_defecto: str = "") -> str:
        """Pide un texto y devuelve el valor por defecto si no se escribe nada."""
