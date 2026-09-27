"""Pruebas de la geometría: ``Posicion`` y ``Movimiento``.

Son las pruebas más básicas del proyecto y aun así encuentran trampas
interesantes, porque son las clases que usan ``dataclass`` con ``frozen`` y
``order`` y de las que dependen todos los cálculos de casillas del tablero.
"""

import pytest

from models.errores import ErrorAjedrez, MovimientoIlegal
from models.posicion import Movimiento, Posicion


# ----------------------------------------------------------------------
# Posicion
# ----------------------------------------------------------------------

class TestPosicion:
    def test_se_construye_desde_coordenadas(self):
        # La columna 4 y la fila 3 son la casilla e4 (la columna va de 0=a a
        # 7=h y la fila de 0=1 a 7=8, así que la fila 3 es la cuarta fila).
        posicion = Posicion(4, 3)
        assert posicion.columna == 4
        assert posicion.fila == 3

    def test_notacion_usa_letra_y_numero(self):
        assert Posicion(4, 3).notacion == "e4"
        assert Posicion(0, 0).notacion == "a1"
        assert Posicion(7, 7).notacion == "h8"

    def test_desde_notacion_acepta_mayusculas_y_espacios(self):
        # Quien pega una posición de una web suele escribirla en mayúsculas.
        assert Posicion.desde_notacion("E4") == Posicion(4, 3)
        assert Posicion.desde_notacion(" e4 ") == Posicion(4, 3)

    @pytest.mark.parametrize(
        "columna,fila",
        [
            (-1, 0),  # columna negativa
            (8, 0),   # columna mayor que 7
            (0, -1),  # fila negativa
            (0, 8),   # fila mayor que 7
        ],
    )
    def test_rechaza_coordenadas_fuera_del_tablero(self, columna, fila):
        with pytest.raises(ErrorAjedrez):
            Posicion(columna, fila)

    def test_rechaza_booleanos_que_son_subclase_de_entero(self):
        # En Python `True` es un `int` (vale 1), así que sin este cuidado
        # `Posicion(True, 0)` significaría "b1" y aceptaría la casilla.
        with pytest.raises(ErrorAjedrez):
            Posicion(True, 0)

    @pytest.mark.parametrize("texto", ["", "e", "e9", "z4", "e44", "4e", "e-4"])
    def test_rechaza_notaciones_invalidas(self, texto):
        with pytest.raises(ErrorAjedrez):
            Posicion.desde_notacion(texto)

    def test_rechaza_notaciones_que_no_son_texto(self):
        with pytest.raises(ErrorAjedrez):
            Posicion.desde_notacion(42)

    def test_es_inmutable(self):
        # Es `frozen=True` a propósito: una casilla es un valor, no algo que
        # se pueda cambiar por error. El tablero la usa como clave de
        # diccionario, y mutarla rompería ese diccionario en silencio.
        posicion = Posicion(4, 3)
        with pytest.raises(Exception):
            posicion.columna = 5

    def test_se_puede_usar_como_clave_de_diccionario(self):
        # Esta es la razón de ser de `frozen=True` y `__hash__`.
        posiciones = {Posicion(4, 3): "rey"}
        posiciones[Posicion(4, 3)] = "peón"
        assert len(posiciones) == 1
        assert posiciones[Posicion(4, 3)] == "peón"

    def test_se_puede_ordenar(self):
        # `order=True` permite comparar y ordenar sin definir `__lt__` a mano.
        # El orden es el de los campos declarados, así que manda la columna y
        # solo cuando dos casillas están en la misma columna se mira la fila.
        assert Posicion(0, 0) < Posicion(1, 0) < Posicion(1, 1)
        assert Posicion(0, 0) < Posicion(0, 1)
        assert sorted([Posicion(7, 7), Posicion(0, 0)]) == [
            Posicion(0, 0),
            Posicion(7, 7),
        ]

    def test_es_oscura_alterna_el_color(self):
        # a1 es oscura, b1 clara, a2 clara: el color alterna en cada paso.
        assert Posicion(0, 0).es_oscura is True
        assert Posicion(1, 0).es_oscura is False
        assert Posicion(0, 1).es_oscura is False

    def test_desplazar_devuelve_none_al_salirse(self):
        # Devolver None en vez de lanzar excepción es lo que permite recorrer
        # el tablero en bucles sin try/except en cada paso.
        assert Posicion(0, 0).desplazar(-1, 0) is None
        assert Posicion(7, 0).desplazar(1, 0) is None
        assert Posicion(4, 3).desplazar(1, 0) == Posicion(5, 3)

    def test_vecinos_devuelve_ocho_en_el_centro_y_tres_en_una_esquina(self):
        assert len(Posicion(3, 3).vecinos()) == 8
        assert len(Posicion(0, 0).vecinos()) == 3

    def test_se_puede_imprimir_como_casilla(self):
        assert str(Posicion(4, 3)) == "e4"


# ----------------------------------------------------------------------
# Movimiento
# ----------------------------------------------------------------------

class TestMovimiento:
    def test_notacion_une_origen_y_destino(self):
        movimiento = Movimiento(Posicion(4, 1), Posicion(4, 3))
        assert movimiento.notacion == "e2-e4"
        assert str(movimiento) == "e2-e4"

    def test_rechaza_origen_igual_a_destino(self):
        # Estar quieto no es una jugada. Se comprueba al construir el
        # movimiento para que el error aparezca en el punto donde se escribe
        # la jugada y no más tarde, al validarla.
        with pytest.raises(MovimientoIlegal):
            Movimiento(Posicion(4, 1), Posicion(4, 1))

    def test_detecta_enroque_por_el_salto_de_dos_columnas(self):
        corto = Movimiento(Posicion(4, 0), Posicion(6, 0))
        largo = Movimiento(Posicion(4, 0), Posicion(2, 0))
        normal = Movimiento(Posicion(4, 0), Posicion(5, 0))
        assert corto.es_enroque is True
        assert largo.es_enroque is True
        # Un paso normal del rey es de una columna: no es enroque.
        assert normal.es_enroque is False

    def test_detecta_avance_recto_por_columna(self):
        assert Movimiento(Posicion(4, 1), Posicion(4, 3)).es_avance_recto is True
        assert Movimiento(Posicion(4, 1), Posicion(5, 2)).es_avance_recto is False

    def test_ida_y_vuelta_conservan_la_forma_serializada(self):
        # Las pruebas de persistencia de todo el proyecto dependen de este
        # viaje de ida y vuelta.
        movimiento = Movimiento(Posicion(4, 1), Posicion(4, 3))
        assert Movimiento.from_dict(movimiento.to_dict()) == movimiento
