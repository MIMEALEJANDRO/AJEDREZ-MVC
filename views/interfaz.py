"""El contrato de la vista: qué necesita **de verdad** el controlador.

Este archivo es la respuesta a una pregunta que aparece en cuanto se escribe el
primer programa: *¿qué necesita exactamente la aplicación para poder mostrar y
pedir cosas?*. La respuesta es una lista de métodos, y esa lista se declara aquí
como un :class:`~typing.Protocol`.

Un ``Protocol`` describe una interfaz sin obligar a heredar de nada. Se escribe
``class Vista(Protocol)`` y una clase que tenga esos métodos **es** una vista, sin
que tenga que declararlo. Esa es toda la ventaja frente a una clase base
abstracta: añadir un método a la interfaz no rompe a las clases que ya existían.

Por qué está en ``views/`` y no en ``controllers/``: el contrato describe lo que
la vista **ofrece**, no lo que el controlador **quiere**. Que lo declare la capa
que lo implementa deja la dependencia en un solo sentido.

Por qué tiene **seis** métodos y no diecisiete
--------------------------------------------

Antes este ``Protocol`` declaraba los diecisiete métodos que tenía la vista de
consola, con sus tres menús y sus cuatro prompts. Cuando se borraron la consola
y la ventana de menús, ese contrato se quedó **mintiendo**: la única vista que
existe (``views.ventana.SalidaDeConsola``) implementa seis de los diecisiete, y
``isinstance(vista, InterfazVista)`` devolvía ``False``.

Un contrato que su propia implementación incumple no es documentación, es una
mentira con nombre de ``Protocol``. Así que el contrato se **redujo a la
verdad**: estos seis métodos son los que el controlador llama hoy por el camino
que la ventana usa de verdad, y ``SalidaDeConsola`` los implementa todos. Eso sí
se comprueba, y hay una prueba que lo comprueba (en ``tests/test_ventana.py``).

Lo que se fue con el recorte, y por qué
----------------------------------------

* **Las tablas ``OPCIONES_*``**, que describían las etiquetas de unos menús que ya
  no se pintan. No las leía nada del programa: solo seaban sus propias pruebas.
* **El bucle de menús del controlador** (``ejecutar`` / ``jugar`` /
  ``gestionar_archivos``) sigue escrito y sigue probado, pero **queda fuera de
  este contrato** a propósito: usa once métodos más que aquí no se declaran, y no
  los llama nadie. Es deuda técnica aceptada, con su coste y su criterio de
  salida anotados en el README. Cuando se podar, este contrato no se toca: los
  seis métodos de aquí son los que hacen falta para el camino vivo.

Uso::

    from views.interfaz import InterfazVista, texto_del_error
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from models.errores import ErrorAjedrez
from models.enums import Color


# --------------------------------------------------------------------------
# El contrato
# --------------------------------------------------------------------------
# La regla que siguen los seis métodos: la vista **muestra** y **pregunta**, y
# nada más. No decide nada (eso es del controlador), no toca el disco (eso es del
# almacenamiento) y no sabe qué es una regla de ajedrez.


@runtime_checkable
class InterfazVista(Protocol):
    """Lo que el controlador necesita de la pantalla que hay.

    Son seis, y no son negotiables por un motivo concreto: la pantalla de
    ``views/ventana.py`` no tiene menús, así que la relación está **invertida**
    (la pantalla tira de las acciones del controlador) y lo único que el
    controlador le pide a la vista es poder hablar con la persona.

    **Escribir** (no preguntan nada)
        ``escribir``, ``titulo``, ``mostrar_mensaje``, ``mostrar_error``.

    **Preguntar** (sí esperan)
        ``pedir_confirmacion`` (sí o no) y ``elegir_color``.

    ``elegir_color`` no pregunta nada en la práctica: la ventana tiene el selector
    de bando siempre visible, así que devuelve lo que ya está marcado en pantalla
    en vez de abrir un diálogo para preguntar lo que se está viendo. Por eso
    está aquí y no como ``pedir_*``.
    """

    def escribir(self, texto: str = "") -> None:
        """Escribe una línea de texto."""

    def titulo(self, texto: str) -> None:
        """Escribe un título destacado."""

    def mostrar_mensaje(self, mensaje: str) -> None:
        """Pinta un mensaje normal."""

    def mostrar_error(self, error: Exception | str) -> None:
        """Pinta un error. Recibe la excepción o su texto ya redactado.

        Acepta las dos cosas a propósito: el controlador captura excepciones del
        dominio (que ya traen el mensaje bueno) y a veces escribe un error
        propio sin excepción detrás (un disco que no se puede escribir). Que la
        vista no tenga que distinguir los dos casos simplifica las dos.
        """

    def pedir_confirmacion(self, pregunta: str) -> bool:
        """Sí o no. ``False`` también si no hay quien responda."""

    def elegir_color(self) -> Color:
        """Con qué bando se juega. En la ventana, el que esté elegido ya."""


# --------------------------------------------------------------------------
# Cómo se leen los errores
# --------------------------------------------------------------------------

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

    Vive aquí, y no dentro de la vista, porque es una decisión sobre *qué* se le
    dice a la persona, no sobre cómo se lo enseña. Si mañana hubiera otra
    pantalla, el texto sería el mismo: es el dominio quien lo redacta.
    """
    if isinstance(error, ErrorAjedrez):
        return f"No se pudo completar la acción: {error}"
    if isinstance(error, str):
        return error
    return f"Error inesperado ({type(error).__name__}): {error}"

