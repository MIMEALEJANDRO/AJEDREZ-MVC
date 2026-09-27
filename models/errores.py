"""Errores del dominio del ajedrez.

Se separan en su propio módulo para que cualquier otra capa del modelo pueda
importarlos sin crear dependencias circulares:

    errores  ->  enums  ->  posicion / pieza  ->  tablero  ->  partida

Todos heredan de ``ErrorAjedrez``, que a su vez hereda de ``ValueError``.
Heredar de ``ValueError`` es una decisión práctica: el código que consume el
modelo (controladores) puede capturarlos con ``except ValueError`` sin
importar nada, igual que se hace con los errores de validación de datos en el
resto de proyectos.
"""


class ErrorAjedrez(ValueError):
    """Error base de las reglas del dominio."""


class MovimientoIlegal(ErrorAjedrez):
    """Se intentó un movimiento que no cumple las reglas.

    Ejemplos: mover una pieza a una casilla donde no puede ir, dejar al rey
    propio en jaque, jugar cuando no es el turno o hacer una promoción
    imposible.
    """


class PartidaTerminada(ErrorAjedrez):
    """Se intentó jugar en una partida que ya terminó.

    Se lanza desde ``Partida.mover`` cuando el estado ya es jaque mate,
    ahogado, tablas o abandono.
    """


class PartidaNoEncontrada(ErrorAjedrez):
    """Se pidió cargar una partida que no existe en el almacenamiento.

    La usan los ``storage`` para no inventar sus propios errores, de modo que
    el controlador siempre capture la misma excepción venga del JSON o del FEN.
    """
