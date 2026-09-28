"""Pruebas del reparto de casillas entre el modelo y la pantalla.

La ventana jugable tiene que decidir en un único sitio dónde cae cada casilla: el
dibujo, el clic y el ratón pasan por ``_a_pantalla`` / ``_de_pantalla``. Cuando el
dibujo invertía una fila y el clic la otra, el tablero salía del revés y, al
pulsar una pieza negra, se movía una blanca: nada en el modelo ni en el
controlador estaba mal.

Estas pruebas no necesitan pantalla. Los tres métodos no tocan el lienzo (son
cálculo puro sobre la posición y el tamaño de la casilla), así que se pueden
llamar sobre un objeto mínimo que solo tenga ``girada``:

    VentanaAjedrez._a_pantalla(ventana_falsa, Posicion(0, 0))

Lo que no se puede comprobar sin abrir una ventana se reparte así:

* ``tests/test_ventana.py`` — el bando, el giro, el botón de FEN y la última
  jugada. Abre una ventana de verdad, así que en un equipo sin pantalla
  necesita ``xvfb-run -a``.
* ``smoke_ventana.py`` — que lo pintado sea exactamente lo que dicen estos
  números, pulsando el tablero con el ratón simulado. Se ejecuta a mano.
"""

from __future__ import annotations

import pytest

from models.enums import Color
from models.posicion import Posicion
from views.ventana import LADO_CASILLA, MARGEN, VentanaAjedrez

TODAS = [Posicion(columna, fila) for columna in range(8) for fila in range(8)]


class VentanaFalsa:
    """Una ventana sin pantalla: solo los métodos de reparto de casillas.

    Se le enganchan los métodos de verdad de ``VentanaAjedrez`` (no son más que
    cálculo sobre la posición y el tamaño de la casilla) y se les da un
    ``girada``, que es lo único que leen. Así se prueban tal cual, sin
    inventarse una copia que podría acertar donde la ventana real falla.
    """

    _a_pantalla = VentanaAjedrez._a_pantalla
    _de_pantalla = VentanaAjedrez._de_pantalla
    _casillas = VentanaAjedrez._casillas

    def __init__(self, girada: bool) -> None:
        self.girada = girada


def a_pantalla(girada: bool, posicion: Posicion) -> tuple[int, int]:
    return VentanaAjedrez._a_pantalla(VentanaFalsa(girada), posicion)


def de_pantalla(girada: bool, x: int, y: int) -> Posicion | None:
    return VentanaAjedrez._de_pantalla(VentanaFalsa(girada), x, y)


def centro(girada: bool, posicion: Posicion) -> tuple[int, int]:
    """El punto donde se pinta una pieza: el centro de su casilla."""
    columna, fila = a_pantalla(girada, posicion)
    return (
        MARGEN + columna * LADO_CASILLA + LADO_CASILLA // 2,
        MARGEN + fila * LADO_CASILLA + LADO_CASILLA // 2,
    )


# ---------------------------------------------------------------------------
# Dónde cae cada casilla
# ---------------------------------------------------------------------------

class TestDondeCaeCadaCasilla:
    def test_sin_girar_el_rey_blanco_abajo_a_la_izquierda(self) -> None:
        assert a_pantalla(False, Posicion(0, 0)) == (0, 7)

    def test_sin_girar_solo_se_invierte_la_fila(self) -> None:
        # a1 se ve abajo, h1 abajo, a8 arriba: las columnas no se mueven.
        assert a_pantalla(False, Posicion(7, 0)) == (7, 7)
        assert a_pantalla(False, Posicion(0, 7)) == (0, 0)
        assert a_pantalla(False, Posicion(7, 7)) == (7, 0)

    def test_girada_es_un_180_y_no_un_espejo(self) -> None:
        # El giro invierte las dos: la columna también. Si solo se invirtiera la
        # fila, el tablero saldría en espejo, con el rey blanco abajo pero a la
        # derecha.
        assert a_pantalla(True, Posicion(0, 0)) == (7, 0)
        assert a_pantalla(True, Posicion(7, 0)) == (0, 0)
        assert a_pantalla(True, Posicion(0, 7)) == (7, 7)
        assert a_pantalla(True, Posicion(7, 7)) == (0, 7)

    def test_las_cuatro_casillas_de_las_esquinas_no_se_confunden(self) -> None:
        for girada in (False, True):
            assert a_pantalla(girada, Posicion(0, 0)) != a_pantalla(girada, Posicion(7, 0))
            assert a_pantalla(girada, Posicion(0, 0)) != a_pantalla(girada, Posicion(0, 7))
            assert a_pantalla(girada, Posicion(7, 7)) != a_pantalla(girada, Posicion(0, 7))

    @pytest.mark.parametrize("girada", [False, True])
    def test_las_64_casillas_caen_en_64_sitios_distintos(self, girada: bool) -> None:
        assert len({a_pantalla(girada, posicion) for posicion in TODAS}) == 64

    @pytest.mark.parametrize("girada", [False, True])
    def test_girar_mandato_va_al_otro_lado(self, girada: bool) -> None:
        # La casilla simétrica respecto del centro tiene que estar justo enfrente.
        for posicion in TODAS:
            columna, fila = a_pantalla(girada, posicion)
            assert a_pantalla(girada, Posicion(7 - posicion.columna, 7 - posicion.fila)) == (
                7 - columna,
                7 - fila,
            )


# ---------------------------------------------------------------------------
# La otra mitad: del clic a la casilla
# ---------------------------------------------------------------------------

class TestDelClicALaCasilla:
    @pytest.mark.parametrize("girada", [False, True])
    @pytest.mark.parametrize("posicion", TODAS, ids=lambda p: p.notacion)
    def test_dibujar_y_pulsar_llegan_a_la_misma_casilla(
        self, girada: bool, posicion: Posicion
    ) -> None:
        # El contrato que no puede romperse: si se ve una pieza en un sitio, al
        # pulsar ese sitio se mueve esa pieza.
        x, y = centro(girada, posicion)
        assert de_pantalla(girada, x, y) == posicion

    @pytest.mark.parametrize("girada", [False, True])
    def test_cualquier_punto_de_la_casilla_llega_a_ella(self, girada: bool) -> None:
        # También en los bordes: la casilla se elige por el suelo, no por su
        # centro exacto.
        for posicion in (Posicion(0, 0), Posicion(4, 1), Posicion(7, 7), Posicion(3, 4)):
            x0, y0 = a_pantalla(girada, posicion)
            for dx in (1, LADO_CASILLA // 2, LADO_CASILLA - 1):
                for dy in (1, LADO_CASILLA // 2, LADO_CASILLA - 1):
                    x = MARGEN + x0 * LADO_CASILLA + dx
                    y = MARGEN + y0 * LADO_CASILLA + dy
                    assert de_pantalla(girada, x, y) == posicion

    @pytest.mark.parametrize("girada", [False, True])
    @pytest.mark.parametrize("posicion", TODAS, ids=lambda p: p.notacion)
    def test_las_esquinas_de_la_casilla_tambien_llegan_a_ella(
        self, girada: bool, posicion: Posicion
    ) -> None:
        # Y al revés, en el otro sentido: del hueco en pantalla a la casilla. Con
        # los cuatro vértices, que son los que se tocan justo en el borde.
        x0, y0 = a_pantalla(girada, posicion)
        for x in (
            MARGEN + x0 * LADO_CASILLA,
            MARGEN + (x0 + 1) * LADO_CASILLA - 1,
        ):
            for y in (
                MARGEN + y0 * LADO_CASILLA,
                MARGEN + (y0 + 1) * LADO_CASILLA - 1,
            ):
                assert de_pantalla(girada, x, y) == posicion

    @pytest.mark.parametrize(
        "x, y",
        [
            (-1, 0),
            (0, -1),
            (MARGEN - 1, MARGEN - 1),
            (MARGEN + 8 * LADO_CASILLA, MARGEN),
            (MARGEN, MARGEN + 8 * LADO_CASILLA),
            (9999, 9999),
        ],
    )
    @pytest.mark.parametrize("girada", [False, True])
    def test_fuera_del_tablero_no_hay_casilla(self, girada: bool, x: int, y: int) -> None:
        assert de_pantalla(girada, x, y) is None

    def test_el_letrero_de_las_filas_no_es_una_casilla(self) -> None:
        # El margen de la izquierda está fuera del tablero: pulsarlo no puede
        # devolver una casilla ni una de la primera columna.
        x = MARGEN // 2
        for fila in range(8):
            assert de_pantalla(False, x, MARGEN + fila * LADO_CASILLA + 1) is None


# ---------------------------------------------------------------------------
# El recorrido que usan dibujo, clic y ratón
# ---------------------------------------------------------------------------

class TestElRecorrido:
    @pytest.mark.parametrize("girada", [False, True])
    def test_las_64_casillas_del_modelo_aparecen_una_vez(self, girada: bool) -> None:
        recorrido = list(VentanaAjedrez._casillas(VentanaFalsa(girada)))
        assert [posicion for posicion, _, _ in recorrido] == TODAS

    @pytest.mark.parametrize("girada", [False, True])
    def test_y_cada_una_con_el_sitio_que_le_corresponde(self, girada: bool) -> None:
        for posicion, columna, fila in VentanaAjedrez._casillas(VentanaFalsa(girada)):
            assert (columna, fila) == a_pantalla(girada, posicion)
