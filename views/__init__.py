"""Capa de vista: la presentación en consola.

Solo se exporta la vista, por la misma razón que en las otras capas: quien
muestra algo en pantalla no necesita saber cómo se llaman los menús ni cómo se
pide un texto, solo tiene que llamarlos.
"""

from views.partida_view import PartidaView

__all__ = ["PartidaView"]
