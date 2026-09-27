"""Capa de modelo: las entidades y las reglas del ajedrez.

Nada de esta capa usa ``input()`` ni ``print()``, ni sabe que existen archivos
o que hay una persona delante. Solo recibe datos y devuelve objetos o
excepciones, que es lo que la hace comprobable sin terminal.

Los módulos de esta capa se pueden leer en orden, porque cada uno solo importa
de los que le preceden en la cadena::

    errores  ->  enums  ->  posicion / pieza  ->  tablero  ->  partida

* ``errores`` — las excepciones del dominio. No importa nada, y por eso
  cualquier otra capa puede usarlas sin crear ciclos.
* ``enums`` — los conjuntos cerrados de valores: ``Color``, ``TipoPieza`` y
  ``EstadoPartida``, más las tablas de traducción a FEN.
* ``posicion`` — la geometría: la casilla (``Posicion``) y el par
  origen/destino (``Movimiento``). No saben nada de reglas.
* ``pieza`` — qué es una pieza: color, tipo y casilla. No sabe moverse.
* ``tablero`` — todas las reglas de movimiento, el jaque y el FEN.
* ``partida`` — el estado que depende de la historia: turno, resultado,
  historial, repeticiones y fin de partida.

Este ``__init__`` reexporta lo más usado para que el resto del programa
pueda escribir ``from models import Partida, Color`` en vez de acordarse de
qué módulo tenía cada cosa. Los módulos siguen siendo importables por separado
(``from models.tablero import Tablero``), que es lo que se usa al probar una
pieza concreta.
"""

from models.enums import Color, EstadoPartida, TipoPieza
from models.errores import (
    ErrorAjedrez,
    MovimientoIlegal,
    PartidaNoEncontrada,
    PartidaTerminada,
)
from models.pieza import Pieza
from models.posicion import Movimiento, Posicion
from models.tablero import Tablero
from models.partida import Partida

# Se listan en `__all__` para dejar claro qué es parte de la API pública del
# modelo. Es lo que además usan las herramientas de análisis estático para
# detectar imports que no existen (y no se importa ``__all__`` aquí, que es lo
# único que realmente no hace falta en el resto del programa).
__all__ = [
    "Color",
    "EstadoPartida",
    "TipoPieza",
    "ErrorAjedrez",
    "MovimientoIlegal",
    "PartidaNoEncontrada",
    "PartidaTerminada",
    "Pieza",
    "Movimiento",
    "Posicion",
    "Tablero",
    "Partida",
]
