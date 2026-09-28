"""La pieza: color, tipo y casilla en la que está.

Es una entidad "de datos" con comportamiento mínimo (un par de propiedades y
la capacidad de copiarse en otra casilla). Toda la lógica de *cómo se mueve*
vive en ``Tablero``, no aquí: es la frontera clara entre "qué hay en el tablero"
y "qué se puede hacer con ello".
"""

from __future__ import annotations

from dataclasses import dataclass

from models.enums import LETRAS_FEN, Color, TipoPieza
from models.errores import ErrorAjedrez
from models.posicion import Posicion

# Símbolos Unicode para dibujar el tablero en consola. Los blancos usan las
# piezas "blancas" (♔♕♖♗♘♙) y los negros las "negras" (♚♛♜♝♞♟), que es la
# convención que usan los programas de ajedrez de consola.
SIMBOLOS = {
    (TipoPieza.REY, Color.BLANCO): "♔",
    (TipoPieza.DAMA, Color.BLANCO): "♕",
    (TipoPieza.TORRE, Color.BLANCO): "♖",
    (TipoPieza.ALFIL, Color.BLANCO): "♗",
    (TipoPieza.CABALLO, Color.BLANCO): "♘",
    (TipoPieza.PEON, Color.BLANCO): "♙",
    (TipoPieza.REY, Color.NEGRO): "♚",
    (TipoPieza.DAMA, Color.NEGRO): "♛",
    (TipoPieza.TORRE, Color.NEGRO): "♜",
    (TipoPieza.ALFIL, Color.NEGRO): "♝",
    (TipoPieza.CABALLO, Color.NEGRO): "♞",
    (TipoPieza.PEON, Color.NEGRO): "♟",
}

# Un peón solo puede promocionar a estas cuatro piezas (nunca a peón ni a rey).
TIPOS_PROMOCION = (TipoPieza.DAMA, TipoPieza.TORRE, TipoPieza.ALFIL, TipoPieza.CABALLO)

# Aceptamos varias formas de escribir la promoción: la palabra en español, la
# letra de FEN (q, r, b, n) y abreviaturas de una letra (d, t, a, c).
LETRAS_PROMOCION = {
    "dama": TipoPieza.DAMA,
    "d": TipoPieza.DAMA,
    "q": TipoPieza.DAMA,
    "torre": TipoPieza.TORRE,
    "t": TipoPieza.TORRE,
    "r": TipoPieza.TORRE,
    "alfil": TipoPieza.ALFIL,
    "a": TipoPieza.ALFIL,
    "b": TipoPieza.ALFIL,
    "caballo": TipoPieza.CABALLO,
    "c": TipoPieza.CABALLO,
    "n": TipoPieza.CABALLO,
}


@dataclass(slots=True)
class Pieza:
    """Pieza del tablero con su color, tipo y casilla actual.

    ``slots=True`` es la misma decisión que en ``Posicion`` y por el mismo
    motivo: ``clonar`` construye una copia de cada pieza del tablero, así que
    estas piezas se crean y se leen millones de veces en un perft. Sin el
    diccionario de atributos que Python pone por defecto en cada objeto, crear
    una pieza y leer sus campos es más rápido y ocupa menos.
    """

    color: Color
    tipo: TipoPieza
    posicion: Posicion

    def __post_init__(self) -> None:
        """Valida los tipos de los atributos.

        Sin esto, ``Pieza("blanco", "rey", ...)`` dejaría pasar datos basura y
        el error aparecería más tarde y más lejos, en la generación de
        movimientos, que es mucho más difícil de depurar.
        """
        if not isinstance(self.color, Color):
            raise ErrorAjedrez("El color de la pieza debe ser un valor de Color.")
        if not isinstance(self.tipo, TipoPieza):
            raise ErrorAjedrez("El tipo de la pieza debe ser un valor de TipoPieza.")
        if not isinstance(self.posicion, Posicion):
            raise ErrorAjedrez("La posición de la pieza debe ser una Posicion.")

    @property
    def nombre(self) -> str:
        """Nombre descriptivo, por ejemplo "Peón blanco"."""
        return f"{self.tipo.nombre_legible} {self.color.value}"

    @property
    def simbolo(self) -> str:
        """Símbolo Unicode para dibujar la pieza."""
        return SIMBOLOS[(self.tipo, self.color)]

    @property
    def letra_fen(self) -> str:
        """Letra con la que la pieza se representa en un FEN."""
        return LETRAS_FEN[(self.tipo, self.color)]

    @property
    def esta_en_promocion(self) -> bool:
        """True si un peón está en la última fila y debe promocionar."""
        return self.tipo is TipoPieza.PEON and self.posicion.fila in (0, 7)

    def con_posicion(self, posicion: Posicion) -> Pieza:
        """Devuelve una *copia* de la pieza colocada en otra casilla.

        Se usa al simular movimientos y al mover la torre en el enroque: nunca
        se muta la pieza original, se crea otra. Así el tablero que se clonó
        para comprobar la legalidad de una jugada no puede contaminar al real.
        """
        return Pieza(self.color, self.tipo, posicion)

    def to_dict(self) -> dict:
        """Serializa la pieza (usada por la persistencia)."""
        return {
            "color": self.color.value,
            "tipo": self.tipo.value,
            "posicion": self.posicion.notacion,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Pieza:
        """Reconstruye la pieza desde su forma serializada."""
        return cls(
            Color(data["color"]),
            TipoPieza(data["tipo"]),
            Posicion.desde_notacion(data["posicion"]),
        )

    def __str__(self) -> str:
        return f"{self.nombre} en {self.posicion.notacion}"
