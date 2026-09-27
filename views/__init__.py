"""Capa de vista: la presentación, en consola o en ventana.

Hay dos vistas y un contrato:

* ``PartidaView`` — la consola, la de siempre.
* ``VistaGUI`` — la ventana de ``tkinter``, en ``views.vista_gui``.
* ``InterfazVista`` — el contrato que cumple cualquiera de las dos.

Se exportan aquí la vista de consola y el contrato por la misma razón que en
las otras capas: quien muestra algo en pantalla no necesita saber cómo se llaman
los menús ni cómo se pide un texto, solo tiene que llamarlos.

Y por qué ``VistaGUI`` **no** se exporta desde aquí: importarla carga
``tkinter``, y entonces cualquier ``import views.partida_view`` —el del
lanzamiento de la consola, o el de las pruebas— necesitaría que tkinter
estuviera instalado. Que se importe solo quien la va a usar
(``from views.vista_gui import VistaGUI``) mantiene la consola sin esa
dependencia.
"""

from views.interfaz import InterfazVista
from views.partida_view import PartidaView

__all__ = ["InterfazVista", "PartidaView"]
