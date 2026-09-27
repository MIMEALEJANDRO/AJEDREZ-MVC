"""Enumeraciones del dominio: color, tipo de pieza y estado de la partida.

Son la forma más simple de expresar "conjuntos cerrados de valores" del
dominio. Al ser ``Enum``, comparar es seguro (``es`` / ``is``), el repr es
legible al depurar y se serializan sin problemas en JSON (guardando ``.value``).
"""

from enum import Enum


class Color(Enum):
    """Color de una pieza o del turno en juego.

    ``BLANCO`` = blancas (mueven primero), ``NEGRO`` = negras.
    """

    BLANCO = "blanco"
    NEGRO = "negro"

    @property
    def contrario(self) -> Color:
        """Devuelve el color opuesto.

        Es la operación que más se usa en las reglas: "el equipo contrario",
        "no puede dejar en jaque al rey contrario", etc.
        """
        return Color.NEGRO if self is Color.BLANCO else Color.BLANCO

    @property
    def letra_fen(self) -> str:
        """Letra con la que el FEN representa el turno: ``w`` o ``b``."""
        return "w" if self is Color.BLANCO else "b"

    @property
    def nombre_legible(self) -> str:
        """Texto para mostrar en pantalla: "Blancas" / "Negras"."""
        return "Blancas" if self is Color.BLANCO else "Negras"

    @classmethod
    def desde_texto(cls, texto: str) -> Color:
        """Convierte texto del usuario ("blancas", "B", "negro"...) en ``Color``.

        Lo usa el controlador cuando el jugador elige color desde un menú.
        """
        if not isinstance(texto, str):
            raise ValueError("El color debe escribirse como texto.")
        limpio = texto.strip().lower()
        if limpio in ("blanco", "blanca", "blancas", "b", "w", "1"):
            return cls.BLANCO
        if limpio in ("negro", "negra", "negras", "n", "2"):
            return cls.NEGRO
        raise ValueError(f"Color desconocido: {texto!r}. Use 'blancas' o 'negras'.")


class TipoPieza(Enum):
    """Tipos de pieza existentes en el tablero.

    Los valores son las palabras en español que se usan en toda la aplicación
    (en el menú, en los mensajes de error y en el JSON guardado).
    """

    PEON = "peon"
    CABALLO = "caballo"
    ALFIL = "alfil"
    TORRE = "torre"
    DAMA = "dama"
    REY = "rey"

    # Nota: aquí no hay ``letra_fen`` a propósito. La letra del FEN depende del
    # *color* (mayúscula = blancas, minúscula = negras), así que no se puede
    # derivar del tipo de pieza solo. La propiedad correcta es
    # ``Pieza.letra_fen``, que sí conoce ambos datos.

    @property
    def nombre_legible(self) -> str:
        """Texto con la inicial en mayúscula para mostrar en pantalla."""
        return NOMBRES[self.value]

    @property
    def es_pieza_larga(self) -> bool:
        """True para torre, dama y rey (las que se nombran con letra en la notación)."""
        return self in (TipoPieza.TORRE, TipoPieza.DAMA, TipoPieza.REY)


class EstadoPartida(Enum):
    """Situación de la partida; se recalcula después de cada jugada."""

    EN_CURSO = "en curso"
    JQUE_MATE = "jaque mate"
    AHOGADO = "ahogado"
    TABLAS = "tablas"
    ABANDONO = "abandono"

    @property
    def terminada(self) -> bool:
        """True si la partida ya no admite más jugadas."""
        return self is not EstadoPartida.EN_CURSO

    @property
    def nombre_legible(self) -> str:
        """Cómo se escribe el estado para quien lo lee: "Jaque mate", "Tablas"...

        Vive en el enum y no en la vista a propósito. Que un estado sea "jaque
        mate" y no "Jaque mate" es información del dominio (el valor es lo que
        se serializa y lo que comparan las pruebas), pero *cómo se escribe*
        cuando se lo enseñas a alguien no es de la consola: lo necesita igual
        una ventana, un PDF o un botón. Si la tabla viviera en la vista,
        cualquier otra pantalla tendría que reinventarla.
        """
        return ETIQUETAS_ESTADO[self]


# --------------------------------------------------------------------------
# Tablas de traducción (letra FEN y nombre legible) de cada tipo de pieza.
# Se definen aquí porque dependen de los enums de este mismo módulo.
# --------------------------------------------------------------------------

NOMBRES = {
    "peon": "Peón",
    "caballo": "Caballo",
    "alfil": "Alfil",
    "torre": "Torre",
    "dama": "Dama",
    "rey": "Rey",
}

# (tipo, color) -> letra. El FEN usa mayúsculas para blancas y minúsculas
# para negras, por eso basta con guardar la versión blanca y bajar().
LETRAS_FEN = {
    (TipoPieza.REY, Color.BLANCO): "K",
    (TipoPieza.DAMA, Color.BLANCO): "Q",
    (TipoPieza.TORRE, Color.BLANCO): "R",
    (TipoPieza.ALFIL, Color.BLANCO): "B",
    (TipoPieza.CABALLO, Color.BLANCO): "N",
    (TipoPieza.PEON, Color.BLANCO): "P",
    (TipoPieza.REY, Color.NEGRO): "k",
    (TipoPieza.DAMA, Color.NEGRO): "q",
    (TipoPieza.TORRE, Color.NEGRO): "r",
    (TipoPieza.ALFIL, Color.NEGRO): "b",
    (TipoPieza.CABALLO, Color.NEGRO): "n",
    (TipoPieza.PEON, Color.NEGRO): "p",
}

# Inversa para poder *parsear* un FEN: letra en minúscula -> tipo de pieza.
LETRAS_FEN_INVERSAS = {letra.lower(): tipo for (tipo, _), letra in LETRAS_FEN.items()}

# Cómo se escribe cada estado de partida. Se declara aquí (y no en la vista)
# porque es el mismo dato para cualquier forma de mostrarlo, y porque
# ``EstadoPartida.nombre_legible`` la consulta.
ETIQUETAS_ESTADO = {
    EstadoPartida.EN_CURSO: "En curso",
    EstadoPartida.JQUE_MATE: "Jaque mate",
    EstadoPartida.AHOGADO: "Ahogado (tablas por rey sin salida)",
    EstadoPartida.TABLAS: "Tablas",
    EstadoPartida.ABANDONO: "Abandono",
}
