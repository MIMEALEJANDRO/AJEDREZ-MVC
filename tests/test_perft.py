"""Pruebas de regresión de perft: el motor de reglas, contando jugadas.

``perft(n)`` es el número de rutas de ``n`` jugadas legales que hay desde una
posición. No dice si una jugada es buena: dice cuántas hay, y eso obliga a que
todo cuadre a la vez, porque cualquier error de una regla (un enroque que no se
debe permitir, un peón que no captura al paso, una promoción que se pierde) sale
inmediato como un número que no coincide.

Los valores de referencia están en ``perft_ajedrez.POSICIONES`` y vienen de
``python-chess``. Aquí se comprueban como pruebas de ``pytest`` para que una
regresión de reglas la vea cualquier ``python -m pytest``, y no solo quien se
dedique a ejecutar el script de perft a mano.

Por qué hay dos tipos de prueba
-------------------------------

* **Los números de la tabla** (``test_perft_cuadra_con_la_referencia``) son la
  red de seguridad final. Si el generador de jugadas se equivoca, el número no
  cuadra.
* **El camino rápido contra el lento** (``test_el_camino_rapido_no_se_diferencia_del_lento``)
  existe porque la generación de jugadas tiene dos caminos: uno que clona el
  tablero por cada candidata y otro que decide con el análisis de las clavadas.
  Los dos tienen que dar **exactamente** la misma lista. Esta prueba es más
  barata que el perft y además señala el fallo mucho más cerca: si las dos
  listas no coinciden, dice exactamente qué jugada acepta una y no la otra.

Las dos se necesitan. La segunda es la que detecta un error en la optimización
(y lo localize al instante), pero no comprueba las reglas en sí: si las dos
rutas estuvieran igual de equivocadas, las dos pruebas pasarían. Eso lo
comprueba la primera.
"""

from __future__ import annotations

import pytest

from models.enums import Color
from models.partida import Partida
from models.posicion import Movimiento
from models.tablero import Tablero
from perft_ajedrez import POSICIONES, perft

# Las posiciones cuyo perft(3) es lo bastante barato para ir en cada ejecución
# de las pruebas. Las otras tres (Kiwipete, Enroque mixto y Jaque) se quedan en
# perft(2) aquí y su perft(3) lo comprueba el trabajo de CI, que sí puede
# tardar.
RAPIDAS_A_FONDO = ("Inicial", "Al paso")


def tablero_de(nombre: str) -> tuple[Tablero, Color]:
    """El tablero y el turno de una de las posiciones de la tabla de perft."""
    for candidato, fen, _ in POSICIONES:
        if candidato == nombre:
            partida = Partida.desde_fen(fen) if fen else Partida()
            return partida.tablero, partida.turno
    raise AssertionError(f"La posición {nombre!r} no está en la tabla de perft.")


def esperado_de(nombre: str) -> list[int]:
    """Los valores de referencia de una de las posiciones de la tabla."""
    for candidato, _, esperados in POSICIONES:
        if candidato == nombre:
            return esperados
    raise AssertionError(f"La posición {nombre!r} no está en la tabla de perft.")


# ---------------------------------------------------------------------------
# 1. Los números de la tabla
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nombre", [nombre for nombre, _, _ in POSICIONES])
@pytest.mark.parametrize("profundidad", [1, 2])
def test_perft_cuadra_con_la_referencia(nombre, profundidad):
    # perft(1) y perft(2) en las seis posiciones. Son unos milliseconds y ya
    # pillan de cabeza los errores más gordos; los valores más profundos están
    # más abajo y en el trabajo de CI.
    tablero, turno = tablero_de(nombre)
    assert perft(tablero, turno, profundidad) == esperado_de(nombre)[profundidad - 1]


@pytest.mark.parametrize("nombre", RAPIDAS_A_FONDO)
def test_perft_de_tres_jugadas_also_en_partida(nombre):
    # perft(3) en las dos posiciones que salen a cuenta. "Al paso" está aquí a
    # propósito: fue el perft(3) el que destapó un error de la captura al paso,
    # porque en perft(2) el número ya cuadraba.
    tablero, turno = tablero_de(nombre)
    assert perft(tablero, turno, 3) == esperado_de(nombre)[2]


# ---------------------------------------------------------------------------
# 2. El camino rápido tiene que decir lo mismo que el lento
# ---------------------------------------------------------------------------

def _legales_pero_lento(tablero: Tablero, color: Color) -> list[Movimiento]:
    """Las jugadas legales filtradas una a una con ``es_legal`` (con clon).

    Es el camino caro: clona el tablero por cada candidata y comprueba si el rey
    propio queda amenazado. Es el que se quiere dejar de usar en el bucle, pero
    sigue siendo la referencia: no depende del análisis de clavadas, así que si
    los dos caminos discrepan, el que se equivoca es el nuevo.
    """
    salida = []
    for pieza in tablero.piezas(color):
        for destino in tablero._destinos_de(pieza, incluir_enroque=True):
            movimiento = Movimiento(pieza.posicion, destino)
            if tablero.es_legal(movimiento):
                salida.append(movimiento)
    return salida


def _camina(tab_tablero: Tablero, color: Color, camino: str, profundidad: int) -> None:
    """Compara los dos caminos en este nodo y en los de debajo, y avisa del fallo."""
    rapidas = set(tab_tablero.movimientos_legales(color))
    lentas = set(_legales_pero_lento(tab_tablero, color))
    assert rapidas == lentas, (
        f"los dos caminos no coinciden tras {camino or 'la posición inicial'}"
        f" (turno de {color.value}):"
        f"\n  solo acepta el rápido: {sorted(m.notacion for m in rapidas - lentas)}"
        f"\n  solo acepta el lento:  {sorted(m.notacion for m in lentas - rapidas)}"
    )
    if profundidad == 0:
        return
    for movimiento in rapidas:
        siguiente = tab_tablero.clonar()
        pieza = siguiente.obtener(movimiento.origen)
        capturada = siguiente._aplicar(movimiento)
        # Los derechos de enroque no los lleva el tablero (no sabe de reglas de
        # partida), así que se preguntan a la clase que sí sabe, igual que hace
        # ``perft_ajedrez``.
        reglas = type("SoloTablero", (), {})()
        reglas.tablero = siguiente
        Partida._registrar_derechos_enroque(reglas, movimiento, pieza, capturada)
        _camina(siguiente, color.contrario, f"{camino}{movimiento.notacion} ", profundidad - 1)


@pytest.mark.parametrize("nombre", [nombre for nombre, _, _ in POSICIONES])
def test_el_camino_rapido_no_se_diferencia_del_lento(nombre):
    # Dos jugadas de profundidad en las seis posiciones. Es la prueba que
    # protege la optimización: si el camino rápido acepta una jugada ilegal (o
    # rechaza una legal), salta aquí con el nombre de la jugada, que es justo lo
    # que hace falta para arreglarlo.
    tablero, turno = tablero_de(nombre)
    _camina(tablero, turno, "", 1)
