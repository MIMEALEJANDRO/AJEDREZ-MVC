"""Pruebas de los enums y de las piezas.

Son pruebas cortas de "contrato": comprueban que los enums se comparan bien,
que las traducciones a FEN y a texto son las esperadas y que ``Pieza`` valida
lo que recibe. Si algo aquí falla, casi siempre significa que se ha roto una
convención que usan muchas otras cosas del proyecto.
"""

import pytest

from models.enums import LETRAS_FEN, Color, EstadoPartida, TipoPieza
from models.errores import ErrorAjedrez
from models.pieza import LETRAS_PROMOCION, Pieza
from models.posicion import Posicion


class TestColor:
    def test_contrario_es_el_opuesto(self):
        assert Color.BLANCO.contrario is Color.NEGRO
        assert Color.NEGRO.contrario is Color.BLANCO

    def test_letra_fen_del_turno(self):
        # Son las letras del campo 2 del FEN: w de white, b de black.
        assert Color.BLANCO.letra_fen == "w"
        assert Color.NEGRO.letra_fen == "b"

    def test_nombre_legible(self):
        assert Color.BLANCO.nombre_legible == "Blancas"
        assert Color.NEGRO.nombre_legible == "Negras"

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("blancas", Color.BLANCO),
            ("Blancas", Color.BLANCO),
            ("  blanca ", Color.BLANCO),
            ("b", Color.BLANCO),
            ("w", Color.BLANCO),
            ("negras", Color.NEGRO),
            ("N", Color.NEGRO),
        ],
    )
    def test_desde_texto_acepta_varias_formas(self, texto, esperado):
        # Quien elige color en un menú escribe de varias maneras; que el
        # modelo lo entienda evita tener que normalizar en la vista.
        assert Color.desde_texto(texto) is esperado

    def test_desde_texto_rechaza_lo_desconocido(self):
        with pytest.raises(ValueError):
            Color.desde_texto("azul")

    def test_desde_texto_rechaza_lo_que_no_es_texto(self):
        with pytest.raises(ValueError):
            Color.desde_texto(1)


class TestTipoPieza:
    def test_las_seis_piezas_existen(self):
        # Las seis de cada color son 12; es el número que se comprueba al
        # colocar la posición inicial.
        assert len(list(TipoPieza)) == 6

    def test_nombre_legible_empieza_en_mayuscula(self):
        assert TipoPieza.PEON.nombre_legible == "Peón"
        assert TipoPieza.ALFIL.nombre_legible == "Alfil"

    def test_es_pieza_larga_solo_para_torre_dama_y_rey(self):
        # "Pieza larga" es la que se nombra con una letra en la notación
        # algebraica (T, D, R) en vez de con su nombre.
        assert TipoPieza.TORRE.es_pieza_larga is True
        assert TipoPieza.DAMA.es_pieza_larga is True
        assert TipoPieza.REY.es_pieza_larga is True
        assert TipoPieza.PEON.es_pieza_larga is False
        assert TipoPieza.CABALLO.es_pieza_larga is False
        assert TipoPieza.ALFIL.es_pieza_larga is False

    def test_la_tabla_fen_tiene_las_doce_letras(self):
        # Doce combinaciones: seis tipos por dos colores.
        assert len(LETRAS_FEN) == 12


class TestEstadoPartida:
    def test_solo_cinco_estados(self):
        assert len(list(EstadoPartida)) == 5

    def test_terminada_para_todo_menos_en_curso(self):
        assert EstadoPartida.EN_CURSO.terminada is False
        for estado in (EstadoPartida.JQUE_MATE, EstadoPartida.AHOGADO,
                       EstadoPartida.TABLAS, EstadoPartida.ABANDONO):
            assert estado.terminada is True


class TestPieza:
    def test_crea_una_pieza_valida(self):
        pieza = Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 1))
        assert pieza.color is Color.BLANCO
        assert pieza.tipo is TipoPieza.PEON
        assert pieza.posicion.notacion == "e2"

    @pytest.mark.parametrize(
        "color,tipo,posicion",
        [
            ("blanco", TipoPieza.PEON, Posicion(4, 1)),  # color como texto
            (Color.BLANCO, "peon", Posicion(4, 1)),      # tipo como texto
            (Color.BLANCO, TipoPieza.PEON, "e2"),        # posición como texto
        ],
    )
    def test_rechaza_atributos_del_tipo_equivocado(self, color, tipo, posicion):
        # Sin esta validación, el error aparecería más tarde y más lejos, al
        # generar movimientos, que es mucho más difícil de depurar.
        with pytest.raises(ErrorAjedrez):
            Pieza(color, tipo, posicion)

    def test_nombre_descriptivo(self):
        pieza = Pieza(Color.BLANCO, TipoPieza.CABALLO, Posicion(1, 0))
        assert pieza.nombre == "Caballo blanco"

    def test_simbolo_unicode_correcto_por_color(self):
        # Las piezas blancas usan los símbolos "blancos" (♔) y las negras los
        # "negros" (♚). Es la convención de los programas de ajedrez de
        # consola, y sobre todo hace que se distingan a simple vista.
        blanco = Pieza(Color.BLANCO, TipoPieza.REY, Posicion(4, 0))
        negro = Pieza(Color.NEGRO, TipoPieza.REY, Posicion(4, 7))
        assert blanco.simbolo == "♔"
        assert negro.simbolo == "♚"
        assert blanco.simbolo != negro.simbolo

    def test_letra_fen_difiere_entre_blancas_y_negras(self):
        # Mayúscula para blancas, minúscula para negras. Es el convenio del
        # FEN y lo que hace que el FEN sea legible por otros programas.
        blanco = Pieza(Color.BLANCO, TipoPieza.DAMA, Posicion(3, 0))
        negro = Pieza(Color.NEGRO, TipoPieza.DAMA, Posicion(3, 7))
        assert blanco.letra_fen == "Q"
        assert negro.letra_fen == "q"

    def test_esta_en_promocion_solo_para_peones_en_la_ultima_fila(self):
        assert Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 7)).esta_en_promocion is True
        assert Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 1)).esta_en_promocion is False
        # Una dama en la última fila no está "en promoción": la promoción es
        # solo cosa de peones.
        assert Pieza(Color.BLANCO, TipoPieza.DAMA, Posicion(4, 7)).esta_en_promocion is False

    def test_con_posicion_devuelve_una_copia(self):
        original = Pieza(Color.NEGRO, TipoPieza.TORRE, Posicion(7, 7))
        movida = original.con_posicion(Posicion(0, 0))
        # La original no se toca: es lo que permite simular una jugada en un
        # tablero clonado sin corromper el real.
        assert original.posicion.notacion == "h8"
        assert movida.posicion.notacion == "a1"
        assert movida.tipo is original.tipo

    def test_ida_y_vuelta_conserva_la_pieza(self):
        pieza = Pieza(Color.NEGRO, TipoPieza.CABALLO, Posicion(6, 7))
        copia = Pieza.from_dict(pieza.to_dict())
        assert copia.color is pieza.color
        assert copia.tipo is pieza.tipo
        assert copia.posicion == pieza.posicion

    def test_se_puede_imprimir(self):
        assert str(Pieza(Color.BLANCO, TipoPieza.REY, Posicion(4, 0))) == "Rey blanco en e1"


class TestLetrasDePromocion:
    @pytest.mark.parametrize(
        "texto,tipo",
        [
            ("dama", TipoPieza.DAMA),
            ("d", TipoPieza.DAMA),
            ("q", TipoPieza.DAMA),
            ("torre", TipoPieza.TORRE),
            ("t", TipoPieza.TORRE),
            ("r", TipoPieza.TORRE),
            ("alfil", TipoPieza.ALFIL),
            ("a", TipoPieza.ALFIL),
            ("b", TipoPieza.ALFIL),
            ("caballo", TipoPieza.CABALLO),
            ("c", TipoPieza.CABALLO),
            ("n", TipoPieza.CABALLO),
        ],
    )
    def test_acepta_palabra_inicial_y_letra_de_fen(self, texto, tipo):
        # Se aceptan las tres formas porque las tres se usan de verdad: el
        # nombre en un menú, la inicial al escribir, y la letra del FEN por
        # costumbre de quien ya ha visto notación algebraica.
        assert LETRAS_PROMOCION[texto] is tipo

    def test_no_acepta_rey_ni_peon_como_promocion(self):
        # El diccionario solo tiene las cuatro piezas legales. Si alguien
        # escribe "rey" no está en el diccionario y el error se da en
        # ``Partida._a_tipo_promocion``, que es quien lo traduce.
        assert "rey" not in LETRAS_PROMOCION
        assert "peon" not in LETRAS_PROMOCION
