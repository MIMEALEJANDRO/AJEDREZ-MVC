"""Casillas y movimientos: la geometría del tablero.

``Posicion`` es la dirección de una casilla (columna a-h, fila 1-8) y
``Movimiento`` es el par origen/destino. No saben nada de reglas: no miran el
tablero, no saben qué es el jaque ni qué es un peón. Esa separación es
justamente la que permite que ``Tablero`` los use como datos simples.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.errores import ErrorAjedrez, MovimientoIlegal

# Letras de las columnas. La posición 0 es la columna "a" (la de la izquierda
# desde la perspectiva de las blancas) y va hasta la "h".
COLUMNAS = "abcdefgh"

# Desplazamientos (columnas, filas) del rey. El rey es el "saltador de una
# casilla": por eso el caballo se define como la suma de dos de estos vectores
# y por eso una torre/dama/rey comparten la idea de "saltador" o "deslizador".
DESPLAZAMIENTOS_REY = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))

# Desplazamientos del caballo: ocho combinaciones de "dos y uno".
DESPLAZAMIENTOS_CABALLO = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))


@dataclass(frozen=True, order=True)
class Posicion:
    """Casilla del tablero identificada por columna (0=a .. 7=h) y fila (0=1 .. 7=8).

    Es ``frozen=True`` (inmutable) a propósito: una casilla es un valor, no un
    objeto que se pueda mutar por error. Como además es ``order=True`` y el
    dataclass genera ``__eq__``/``__hash__``, se puede usar directamente como
    clave de diccionario, que es justo lo que hace ``Tablero`` para guardar
    "casilla -> pieza".
    """

    columna: int
    fila: int

    def __post_init__(self) -> None:
        """Valida los rangos al construir la posición.

        ``bool`` es subclase de ``int`` en Python, así que se descarta
        explícitamente para que ``Posicion(True, 0)`` no se acepte.
        """
        if isinstance(self.columna, bool) or isinstance(self.fila, bool):
            raise ErrorAjedrez("La posición debe usar números enteros.")
        if not isinstance(self.columna, int) or not isinstance(self.fila, int):
            raise ErrorAjedrez("La posición debe usar números enteros.")
        if not 0 <= self.columna <= 7:
            raise ErrorAjedrez("La columna debe estar entre 0 (a) y 7 (h).")
        if not 0 <= self.fila <= 7:
            raise ErrorAjedrez("La fila debe estar entre 0 (1) y 7 (8).")

    @classmethod
    def desde_notacion(cls, texto: str) -> Posicion:
        """Construye una posición desde notación algebraica, por ejemplo ``"e4"``.

        Es el punto de entrada de todo lo que viene del usuario: el controlador
        convierte el texto que escribió el jugador en un ``Posicion``.
        """
        if not isinstance(texto, str):
            raise ErrorAjedrez("La posición debe escribirse como texto, por ejemplo 'e4'.")
        limpio = texto.strip().lower()
        if len(limpio) != 2 or limpio[0] not in COLUMNAS or limpio[1] not in "12345678":
            raise ErrorAjedrez(f"Posición inválida: {texto!r}. Use el formato a1-h8.")
        return cls(COLUMNAS.index(limpio[0]), int(limpio[1]) - 1)

    @property
    def notacion(self) -> str:
        """Notación algebraica de la casilla, por ejemplo ``"e4"``."""
        return f"{COLUMNAS[self.columna]}{self.fila + 1}"

    @property
    def es_oscura(self) -> bool:
        """True si la casilla es oscura, para pintar el tablero en la vista.

        En ajedrez la casilla a1 es **oscura**, así que la casilla es oscura
        cuando la suma de columna y fila es par (0+0 en a1). Por eso aquí se
        compara con 0 y no con 1, que es el error fácil al trasladar el
        criterio de "casillas alternas" sin mirar a qué color corresponde
        cada una.
        """
        return (self.columna + self.fila) % 2 == 0

    def desplazar(self, columnas: int, filas: int) -> Posicion | None:
        """Devuelve la casilla desplazada, o ``None`` si se sale del tablero.

        Devolver ``None`` en vez de lanzar excepción es deliberado: al generar
        movimientos hay que "caminar" por el tablero y basta con ignorar los
        destinos que se salen, sin manejar excepciones dentro de los bucles.
        """
        nueva_columna = self.columna + columnas
        nueva_fila = self.fila + filas
        if not (0 <= nueva_columna <= 7 and 0 <= nueva_fila <= 7):
            return None
        return Posicion(nueva_columna, nueva_fila)

    def vecinos(self) -> list[Posicion]:
        """Las ocho casillas adyacentes que están dentro del tablero."""
        encontradas = []
        for columnas, filas in DESPLAZAMIENTOS_REY:
            destino = self.desplazar(columnas, filas)
            if destino is not None:
                encontradas.append(destino)
        return encontradas

    def to_dict(self) -> dict:
        """Serializa la casilla (usada por la persistencia)."""
        return {"columna": self.columna, "fila": self.fila}

    @classmethod
    def from_dict(cls, data: dict) -> Posicion:
        """Reconstruye la casilla desde su forma serializada."""
        return cls(data["columna"], data["fila"])

    def __str__(self) -> str:
        return self.notacion


@dataclass(frozen=True)
class Movimiento:
    """Un movimiento de una casilla a otra.

    Inmutable también, y comparable por valor: eso permite escribir
    ``if movimiento in self.movimientos_disponibles()`` para validar la jugada
    que el jugador ha escrito, que es el uso principal de esta clase.
    """

    origen: Posicion
    destino: Posicion

    def __post_init__(self) -> None:
        if self.origen == self.destino:
            raise MovimientoIlegal("El origen y el destino no pueden ser la misma casilla.")

    @property
    def es_enroque(self) -> bool:
        """True si el rey se mueve dos columnas de golpe (enroque)."""
        return abs(self.destino.columna - self.origen.columna) == 2

    @property
    def es_avance_recto(self) -> bool:
        """True si origen y destino están en la misma columna (peones y torres)."""
        return self.origen.columna == self.destino.columna

    @property
    def notacion(self) -> str:
        """Notación breve del movimiento, por ejemplo ``"e2-e4"``."""
        return f"{self.origen.notacion}-{self.destino.notacion}"

    def to_dict(self) -> dict:
        """Serializa el movimiento (usada por la persistencia)."""
        return {"origen": self.origen.notacion, "destino": self.destino.notacion}

    @classmethod
    def from_dict(cls, data: dict) -> Movimiento:
        """Reconstruye el movimiento desde su forma serializada."""
        return cls(Posicion.desde_notacion(data["origen"]), Posicion.desde_notacion(data["destino"]))

    def __str__(self) -> str:
        return self.notacion
