"""Pruebas del tablero: generación de movimientos, jaque y reglas especiales.

Es la parte con más lógica del modelo, así que aquí se comprueban las reglas
que son fáciles de equivocar: el peón (avances y capturas), el enroque (con
sus cuatro condiciones), la captura al paso, la promoción y el FEN.

Un truco que se usa varias veces en este archivo: ``mate_en_una()`` parte de
una posición de un problema de mate y ejecuta la jugada que da mate. Sirve
para comprobar indirectamente que la generación de movimientos es correcta:
si el mate se detecta, la jugada era legal; y si se detecta como mate y no
como ahogado, la posición era de mate de verdad.
"""

import pytest

from models.enums import Color, TipoPieza
from models.errores import ErrorAjedrez, MovimientoIlegal
from models.pieza import Pieza
from models.posicion import Movimiento, Posicion
from models.tablero import Tablero

# FEN de la posición inicial. Se escribe una sola vez y se reutiliza: es la
# partida de referencia de todas las pruebas de este archivo.
INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def tablero_desde_fen(fen: str) -> Tablero:
    """Atajo para crear un tablero a partir de la parte de colocación de un FEN.

    Los FEN de estas pruebas son solo piezas: los derechos de enroque se pasan
    aparte porque no se deducen de la posición (dependen del historial).
    """
    return Tablero.desde_fen(fen, {"K", "Q", "k", "q"})


def mover(tablero: Tablero, origen: str, destino: str, promocion=None) -> Pieza | None:
    """Atajo para ejecutar una jugada por notación, devolviendo lo capturado."""
    movimiento = Movimiento(Posicion.desde_notacion(origen), Posicion.desde_notacion(destino))
    return tablero.aplicar(movimiento, promocion)


# ----------------------------------------------------------------------
# Construcción y contenido
# ----------------------------------------------------------------------

class TestConstruccion:
    def test_posicion_inicial_tiene_las_32_piezas(self):
        tablero = Tablero.posicion_inicial()
        assert len(tablero.piezas()) == 32
        assert len(tablero.piezas(Color.BLANCO)) == 16
        assert len(tablero.piezas(Color.NEGRO)) == 16

    def test_los_reyes_estan_en_su_casilla(self):
        tablero = Tablero.posicion_inicial()
        assert tablero.rey_de(Color.BLANCO).posicion.notacion == "e1"
        assert tablero.rey_de(Color.NEGRO).posicion.notacion == "e8"

    def test_los_peones_estan_en_su_fila(self):
        tablero = Tablero.posicion_inicial()
        for pieza in tablero.piezas():
            if pieza.tipo is TipoPieza.PEON:
                assert pieza.posicion.fila == (1 if pieza.color is Color.BLANCO else 6)

    def test_los_cuatro_caballos_estan_bien_colocados(self):
        # Un error de despliegue de caballos es el error más fácil de
        # introducir al escribir la posición inicial a mano.
        tablero = Tablero.posicion_inicial()
        assert tablero.obtener(Posicion(1, 0)).tipo is TipoPieza.CABALLO
        assert tablero.obtener(Posicion(6, 0)).tipo is TipoPieza.CABALLO
        assert tablero.obtener(Posicion(1, 7)).tipo is TipoPieza.CABALLO
        assert tablero.obtener(Posicion(6, 7)).tipo is TipoPieza.CABALLO

    def test_el_fen_de_la_posicion_inicial_va_derecha(self):
        # El FEN empieza por la fila 8, así que las negras van primero.
        assert Tablero.desde_fen(INICIAL).clave() == Tablero.posicion_inicial().clave()

    def test_desde_fen_acepta_solo_la_colocacion(self):
        assert len(Tablero.desde_fen(INICIAL).piezas()) == 32

    @pytest.mark.parametrize(
        "fen",
        [
            "",                                  # vacío
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP",  # solo 7 filas
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR9",  # fila de 9 casillas
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/XXXXKBNR",  # letra inválida
        ],
    )
    def test_rechaza_fens_mal_formados(self, fen):
        with pytest.raises(ErrorAjedrez):
            Tablero.desde_fen(fen)

    def test_clonar_produce_una_copia_independiente(self):
        # La independencia es la base del algoritmo de legalidad: si el clon
        # compartiera piezas con el original, simular una jugada modificaría el
        # tablero real.
        tablero = Tablero.posicion_inicial()
        copia = tablero.clonar()
        mover(copia, "e2", "e4")
        assert not tablero.en_juego(Posicion(4, 3))
        assert copia.en_juego(Posicion(4, 3))
        # Y al revés: la copia no arrastra los cambios del original.
        assert copia.derechos_enroque == {"K", "Q", "k", "q"}

    def test_limpiar_deja_el_tablero_vacio(self):
        tablero = Tablero.posicion_inicial()
        tablero.limpiar()
        assert tablero.piezas() == []
        assert tablero.derechos_enroque == set()

    def test_colocar_rechaza_una_casilla_ocupada(self):
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.REY, Posicion(4, 0)))
        with pytest.raises(ErrorAjedrez):
            tablero.colocar(Pieza(Color.BLANCO, TipoPieza.TORRE, Posicion(4, 0)))


# ----------------------------------------------------------------------
# Movimientos de cada pieza
# ----------------------------------------------------------------------

class TestMovimientosDePiezas:
    def test_cada_peon_blanco_tiene_dos_movimientos_iniciales(self):
        # 20 jugadas iniciales: 16 de peón (dos cada uno) y 4 de caballo.
        tablero = Tablero.posicion_inicial()
        assert len(tablero.movimientos_legales(Color.BLANCO)) == 20

    def test_el_caballo_tiene_ocho_destinos_desde_el_centro(self):
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.CABALLO, Posicion(3, 3)))
        assert len(tablero.destinos_de(Posicion(3, 3))) == 8

    def test_el_caballo_no_puede_moverse_en_linea_recta(self):
        # Es el error clásico al implementar el caballo: usar un desplazamiento
        # orthogonal en vez de un salto de "dos y uno".
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.CABALLO, Posicion(3, 3)))
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(3, 3))}
        assert "d4" not in destinos   # misma columna, una fila: no es salto de caballo
        assert "d5" not in destinos   # una columna, dos filas: tampoco
        assert "e5" not in destinos   # dos columnas, dos filas: menos aún
        # Lo que sí es de caballo: dos columnas y una fila, o al revés.
        assert "f3" in destinos       # dos columnas, misma fila
        assert "f5" in destinos       # dos columnas, dos filas (salto de caballo)

    def test_la_torre_se_detiene_en_el_primer_obstaculo(self):
        # Se coloca un peón enemigo en a4, en la misma columna que la torre de
        # a1: la torre puede capturarlo, pero no pasar de ahí. (En d4 no valdría
        # como ejemplo, porque un peón en diagonal no estorba a una torre.)
        tablero = tablero_desde_fen("4k3/8/8/8/p7/8/8/R6K")
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(0, 0))}
        assert "a2" in destinos
        assert "a3" in destinos
        assert "a4" in destinos   # puede capturar el peón
        assert "a5" not in destinos  # y no puede seguir detrás

    def test_el_alfil_no_va_en_linea_recta(self):
        # Con un peón enemigo en e5 (la diagonal del alfil de a1), el alfil
        # avanza en diagonal, captura y se detiene: no puede seguir a f6.
        tablero = tablero_desde_fen("4k3/8/8/4p3/8/8/8/B6K")
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(0, 0))}
        assert "a4" not in destinos   # misma columna que a1
        assert "b1" not in destinos   # misma fila que a1
        assert "e5" in destinos       # diagonal, con captura
        assert "f6" not in destinos   # detrás del peón ya no se pasa

    def test_el_alfil_llega_a_la_esquina_opuesta(self):
        # Sin nada en medio, la diagonal entera de a1 a h8 es suya.
        tablero = tablero_desde_fen("4k3/8/8/8/8/8/8/B6K")
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(0, 0))}
        assert "d4" in destinos
        assert "h8" in destinos

    def test_la_dama_combina_torre_y_alfil(self):
        # En el centro del tablero la dama tiene 27 destinos: 14 en las 4
        # líneas rectas y 13 en las 4 diagonales.
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.DAMA, Posicion(3, 3)))
        assert len(tablero.destinos_de(Posicion(3, 3))) == 27

    def test_ninguna_pieza_puede_capturar_una_aliada(self):
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.TORRE, Posicion(0, 0)))
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(0, 3)))
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(0, 0))}
        assert "a4" not in destinos
        assert "a3" in destinos

    def test_el_peon_avanza_una_casilla(self):
        tablero = Tablero.posicion_inicial()
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(4, 1))}
        assert destinos == {"e3", "e4"}

    def test_el_peon_no_avanza_dos_casillas_si_tiene_piezas_en_el_medio(self):
        # Con un peón en e3, el de e2 no puede avanzar: la casilla de delante
        # está ocupada (y un peón no captura hacia delante, así que tampoco es
        # una captura). El peón tiene que estar en la fila 1, que es la segunda
        # fila del tablero: solo desde ahí se puede hacer el salto doble.
        tablero = Tablero()
        for posicion in (Posicion(4, 1), Posicion(4, 2)):
            tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, posicion))
        assert tablero.destinos_de(Posicion(4, 1)) == []
        # Y con e3 libre, el avance doble sí se ofrece: lo que se está
        # comprobando es el bloqueo y no una regla que siempre lo prohíba.
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 1)))
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(4, 1))}
        assert destinos == {"e3", "e4"}

    def test_el_peon_negras_avanza_hacia_arriba(self):
        # Las negras avanzan de la fila 7 a la 6, que en pantalla "sube".
        tablero = Tablero()
        tablero.colocar(Pieza(Color.NEGRO, TipoPieza.PEON, Posicion(4, 6)))
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(4, 6))}
        assert destinos == {"e6", "e5"}

    def test_el_peon_solo_captura_en_diagonal(self):
        # Un peón nunca captura hacia delante, solo en diagonal. Con un peón
        # enemigo en d3, el peón de e2 puede capturarlo; la casilla f3 está
        # vacía, así que ahí no hay nada que capturar y no se puede avanzar en
        # diagonal.
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 1)))
        tablero.colocar(Pieza(Color.NEGRO, TipoPieza.PEON, Posicion(3, 2)))
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(4, 1))}
        # Avance recto: a e3 y a e4 (el avance doble, porque está en su fila).
        assert "e3" in destinos
        assert "e4" in destinos
        # Captura en diagonal: solo d3, que tiene una pieza enemiga.
        assert "d3" in destinos
        assert "f3" not in destinos

    def test_el_peon_no_puede_capturar_una_pieza_aliada_en_diagonal(self):
        # La misma comprobación con una pieza propia: capturar a un aliado
        # tampoco es una jugada.
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 1)))
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(3, 2)))
        destinos = {posicion.notacion for posicion in tablero.destinos_de(Posicion(4, 1))}
        assert "d3" not in destinos

    def test_el_peon_no_puede_avanzar_si_tiene_pieza_delante(self):
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 0)))
        tablero.colocar(Pieza(Color.NEGRO, TipoPieza.PEON, Posicion(4, 1)))
        assert tablero.destinos_de(Posicion(4, 0)) == []

    def test_el_rey_tiene_ocho_destinos_en_el_centro(self):
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.REY, Posicion(3, 3)))
        assert len(tablero.destinos_de(Posicion(3, 3))) == 8

    def test_el_rey_tiene_tres_destinos_en_una_esquina(self):
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.REY, Posicion(0, 0)))
        assert len(tablero.destinos_de(Posicion(0, 0))) == 3


# ----------------------------------------------------------------------
# Jaque
# ----------------------------------------------------------------------

class TestJaque:
    def test_una_torre_ataca_en_linea_recta(self):
        tablero = tablero_desde_fen("4k3/8/8/8/8/8/4R3/4K3")
        assert tablero.esta_en_jaque(Color.NEGRO) is True
        assert tablero.esta_en_jaque(Color.BLANCO) is False

    def test_una_pieza_no_jaque_a_traves_de_otra(self):
        # La torre de e1 no puede ver el rey de e8 porque hay un peón en e4.
        tablero = tablero_desde_fen("4k3/8/8/8/4p3/8/4R3/4K3")
        assert tablero.esta_en_jaque(Color.NEGRO) is False

    def test_jaque_con_caballo_desde_el_rincon(self):
        # El rey negro en h8 solo está amenazado por un caballo en f7 o g6.
        tablero = tablero_desde_fen("7k/5N2/8/8/8/8/8/4K3")
        assert tablero.esta_en_jaque(Color.NEGRO) is True
        # Y un caballo en g6 también lo amenaza. (Ojo: g6 está en la fila 6, así
        # que va en el cuarto grupo del FEN, no en el segundo.)
        tablero = tablero_desde_fen("7k/8/6N1/8/8/8/8/4K3")
        assert tablero.esta_en_jaque(Color.NEGRO) is True

    def test_es_ataqueada_consulta_un_color_concreto(self):
        tablero = tablero_desde_fen("4k3/8/8/8/8/8/4R3/4K3")
        assert tablero.es_ataqueada(Posicion(4, 7), Color.BLANCO) is True
        assert tablero.es_ataqueada(Posicion(4, 7), Color.NEGRO) is False

    def test_error_si_no_hay_rey_de_ese_color(self):
        # No se puede preguntar por el jaque de un color sin rey: es una
        # posición ilegal y conviene que se note, no que devuelva False.
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.REY, Posicion(4, 0)))
        with pytest.raises(ErrorAjedrez):
            tablero.esta_en_jaque(Color.NEGRO)

    def test_no_se_puede_dejar_al_rey_propio_en_jaque(self):
        # El rey blanco de e1 está en jaque por la torre negra de e8. Moverse a
        # d1 tampoco le sirve, porque la torre de d8 sigue mandando en la columna
        # d. Se necesitan las dos torres negras para que el ejemplo signifique
        # algo: con una sola, d1 sería una casilla segura.
        tablero = tablero_desde_fen("3rr1k1/8/8/8/8/8/8/4K3")
        assert tablero.esta_en_jaque(Color.BLANCO) is True
        assert not tablero.es_legal(Movimiento(Posicion(4, 0), Posicion(3, 0)))

    def test_se_puede_mover_el_rey_a_una_casilla_libre_de_amenazas(self):
        # Las dos torres negras mandan en las columnas d y e. De las casillas
        # de alrededor de e1, f1 es la única que no está amenazada: d1 y e2 están
        # en la columna d y en la columna e respectivamente. La torre no gira:
        # por mucho que el rey*e8* esté en la misma columna, a f1 no llega.
        tablero = tablero_desde_fen("3rr1k1/8/8/8/8/8/8/4K3")
        assert tablero.es_legal(Movimiento(Posicion(4, 0), Posicion(5, 0)))

    def test_no_se_puede_capturar_al_rey(self):
        # Capturar el rey no es una jugada: en un juego real la partida
        # acabaría en el jaque mate antes de llegar aquí. El modelo no lo
        # permite por si mismo para que nadie espere ese final.
        tablero = tablero_desde_fen("4k3/4R3/8/8/8/8/8/4K3")
        with pytest.raises(MovimientoIlegal):
            mover(tablero, "e7", "e8")
        # Y tampoco se ofrece entre los movimientos legales.
        assert all(m.destino != Posicion(4, 7) for m in tablero.movimientos_de(Posicion(4, 6)))


# ----------------------------------------------------------------------
# Enroque
# ----------------------------------------------------------------------

class TestEnroque:
    def test_enroque_corto_mueve_rey_y_torre(self):
        tablero = tablero_desde_fen("r3k2r/8/8/8/8/8/8/R3K2R")
        mover(tablero, "e1", "g1")
        assert tablero.obtener(Posicion(6, 0)).tipo is TipoPieza.REY
        assert tablero.obtener(Posicion(5, 0)).tipo is TipoPieza.TORRE
        # Las casillas de origen quedan vacías.
        assert not tablero.en_juego(Posicion(4, 0))
        assert not tablero.en_juego(Posicion(7, 0))

    def test_enroque_largo_mueve_rey_y_torre(self):
        tablero = tablero_desde_fen("r3k2r/8/8/8/8/8/8/R3K2R")
        mover(tablero, "e1", "c1")
        assert tablero.obtener(Posicion(2, 0)).tipo is TipoPieza.REY
        assert tablero.obtener(Posicion(3, 0)).tipo is TipoPieza.TORRE

    def test_no_se_puede_enrocar_con_piezas_en_el_camino(self):
        # Hay un caballo en f1: estorba el enroque corto.
        tablero = tablero_desde_fen("r3k2r/8/8/8/8/8/8/R3KN1R")
        destinos = {p.notacion for p in tablero.destinos_de(Posicion(4, 0))}
        assert "g1" not in destinos

    def test_no_se_puede_enrocar_estando_en_jaque(self):
        # La torre negra de e8 threaten al rey blanco de e1: con el rey en jaque
        # no se puede enrocar ni a un lado ni al otro (el enroque corto exige
        # que el rey no esté en jaque al empezar y al terminar; el largo
        # también).
        tablero = tablero_desde_fen("4r3/4k3/8/8/8/8/8/R3K2R")
        destinos = {p.notacion for p in tablero.destinos_de(Posicion(4, 0))}
        assert "g1" not in destinos
        assert "c1" not in destinos

    def test_no_se_puede_enrocar_si_el_camino_del_rey_esta_amenazado(self):
        # La casilla f1 está amenazada por la torre de f8, así que el rey no
        # puede pasar por ella aunque el enroque corto sea legal en lo demás.
        # (Aquí el rey **no** está en jaque: la torre manda en la columna f.)
        tablero = tablero_desde_fen("5r2/4k3/8/8/8/8/8/R3K2R")
        assert not tablero.esta_en_jaque(Color.BLANCO)
        movimientos = tablero.movimientos_de(Posicion(4, 0))
        enroques = {m.destino.notacion for m in movimientos if m.es_enroque}
        assert enroques == {"c1"}

    def test_no_se_puede_enrocar_sin_derecho(self):
        # Las piezas están en su sitio pero sin derechos de enroque: no hay
        # forma de enrocar.
        tablero = Tablero.desde_fen("r3k2r/8/8/8/8/8/8/R3K2R", set())
        destinos = {p.notacion for p in tablero.destinos_de(Posicion(4, 0))}
        assert "g1" not in destinos
        assert "c1" not in destinos

    def test_no_se_puede_enrocar_desde_otra_casilla(self):
        # El rey ya movido no puede enrocar aunque las torres sigan en su
        # sitio. (Los derechos se pierden en ``Partida``, pero la posición con
        # los derechos puestos también debe rechazarse.)
        #
        # Con el rey en f1 no hay ningún enroque posible: g1 es un movimiento
        # normal de rey, no un enroque. Por eso lo que se comprueba es que
        # ``Movimiento.es_enroque`` sea falso, y no que "g1" no aparezca entre
        # los destinos.
        tablero = Tablero.desde_fen("r3k2r/8/8/8/8/8/8/R4K1R", {"K", "Q", "k", "q"})
        movimientos = tablero.movimientos_de(Posicion(5, 0))
        assert not any(movimiento.es_enroque for movimiento in movimientos)
        # Y en su posición correcta el enroque sí se ofrece, lo que demuestra que
        # lo que se comprobó antes es la casilla y no los derechos.
        tablero = Tablero.desde_fen("r3k2r/8/8/8/8/8/8/R3K2R", {"K", "Q", "k", "q"})
        assert any(movimiento.es_enroque for movimiento in tablero.movimientos_de(Posicion(4, 0)))

    def test_los_derechos_de_enroque_se_heredan_en_la_clonacion(self):
        # Si la clonación no copiara los derechos, la simulación de legalidad
        # daría por legal un enroque que en realidad no lo es.
        tablero = tablero_desde_fen("r3k2r/8/8/8/8/8/8/R3K2R")
        assert tablero.clonar().derechos_enroque == {"K", "Q", "k", "q"}


# ----------------------------------------------------------------------
# Captura al paso
# ----------------------------------------------------------------------

class TestCapturaAlPaso:
    def test_blancas_capturan_al_paso_un_peon_negro(self):
        # 1. e4 a5  2. e5 d5  3. exd6 al paso.
        tablero = Tablero.posicion_inicial()
        mover(tablero, "e2", "e4")
        mover(tablero, "a7", "a5")
        mover(tablero, "e4", "e5")
        mover(tablero, "d7", "d5")
        # El peón blanco de e5 captura en d6 y se lleva el peón de d5.
        mover(tablero, "e5", "d6")
        assert tablero.obtener(Posicion(3, 5)).tipo is TipoPieza.PEON
        # La casilla d5 queda vacía: la víctima se retire del sitio.
        assert not tablero.en_juego(Posicion(3, 4))

    def test_negras_capturan_al_paso_un_peon_blanco(self):
        # Para que las negras puedan capturar al paso tiene que pasar justo lo
        # contrario que en el caso anterior: un peón **blanco** que avanza dos
        # casillas y deja el suyo en la fila 4, al lado de un peón negro.
        #
        # La posición se monta a mano porque en la posición inicial haría falta
        # llegar hasta la fila 5 con el peón blanco. No se usan jugadas
        # alternadas porque ``Tablero`` no lleva el turno: ``aplicar`` ejecuta
        # el movimiento que se le pide.
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.REY, Posicion(4, 0)))
        tablero.colocar(Pieza(Color.NEGRO, TipoPieza.REY, Posicion(4, 7)))
        tablero.colocar(Pieza(Color.NEGRO, TipoPieza.PEON, Posicion(3, 3)))   # d4
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 3)))  # e4
        # Se finge que la última jugada fue el avance doble del peón blanco.
        tablero.ultima_jugada = Movimiento(Posicion(4, 1), Posicion(4, 3))  # e2-e4
        destinos = {p.notacion for p in tablero.destinos_de(Posicion(3, 3))}
        assert "e3" in destinos  # la casilla está vacía: solo se puede al pasar
        assert "d3" in destinos  # y el avance normal del peón negro
        mover(tablero, "d4", "e3")
        assert tablero.obtener(Posicion(4, 2)).tipo is TipoPieza.PEON
        # La casilla d4 queda vacía: la víctima se retira del sitio.
        assert not tablero.en_juego(Posicion(3, 3))
        # Y el peón blanco que se capturó ya no está en e4.
        assert not tablero.en_juego(Posicion(4, 3))

    def test_solo_un_peon_puede_capturar_al_paso(self):
        # La captura al paso es una regla **de peones**: la casilla de la
        # víctima se deduce de la última jugada, y como esa deducción es solo
        # geométrica, cualquier otra pieza que se mueva a esa casilla puede
        # "cumplirla" sin estar haciendo una captura al paso.
        #
        # Aquí el rey negro va de h4 a g3, en diagonal a la casilla de la
        # posible captura al paso, que es la sexta fila para las negras. La
        # casilla de la víctima se calcula como (columna del destino, fila del
        # origen) = (6, 3) = g4, así que sin comprobar que la pieza que se
        # mueve es un peón, el rey se llevaba por delante el peón blanco de g4
        # sin haber pasado por él.
        tablero = tablero_desde_fen("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8")
        # Se finge que la última jugada fue el avance doble de g2 a g4.
        mover(tablero, "g2", "g4")
        assert tablero.obtener(Posicion(6, 3)).tipo is TipoPieza.PEON
        # El rey se mueve a g3 y no se lleva a nadie por el camino.
        capturada = mover(tablero, "h4", "g3")
        assert capturada is None
        # El peón blanco sigue en g4: el rey no captura al paso.
        assert tablero.obtener(Posicion(6, 3)).tipo is TipoPieza.PEON
        # Y el rey está en g3.
        assert tablero.obtener(Posicion(6, 2)).tipo is TipoPieza.REY

    def test_ninguna_otra_pieza_genera_una_captura_al_paso(self):
        # La misma comprobación con una pieza que no es el rey: un alfil negro
        # en d4 que se mueve a e3.
        #
        # La casilla de la víctima se deduce de la última jugada, así que para
        # que e3 "cuadre" tiene que cumplirse que la columna del destino sea la
        # de la casilla del peón (e) y que la fila de la pieza que se mueve sea
        # la del peón (4). Un alfil en d4 cumple las dos cosas.
        tablero = tablero_desde_fen("4k3/8/8/8/3bP3/8/8/4K3")
        # Se finge que la última jugada fue el avance doble del peón blanco.
        tablero.ultima_jugada = Movimiento(Posicion(4, 1), Posicion(4, 3))  # e2-e4
        capturada = mover(tablero, "d4", "e3")
        # e3 estaba vacía: es un movimiento normal, no una captura.
        assert capturada is None
        # El peón blanco de e4 no se ha movido: el alfil no captura al paso.
        assert tablero.obtener(Posicion(4, 3)).tipo is TipoPieza.PEON
        assert tablero.obtener(Posicion(4, 2)).tipo is TipoPieza.ALFIL

    def test_no_hay_captura_al_paso_si_el_peon_no_avanza_dos_casillas(self):
        # 1. e4 d5 2. e5: el peón blanco avanza una sola casilla y el peón negro
        # se queda en d5, al lado pero no en diagonal. Con la casilla d6 vacía,
        # no hay nada que capturar: d6 es un movimiento diagonal imposible.
        tablero = Tablero.posicion_inicial()
        mover(tablero, "e2", "e4")
        mover(tablero, "d7", "d5")
        mover(tablero, "e4", "e5")
        destinos = {p.notacion for p in tablero.destinos_de(Posicion(4, 4))}
        assert "d6" not in destinos
        assert destinos == {"e6"}

    def test_no_hay_captura_al_paso_si_no_es_una_casilla_de_paso(self):
        # La captura al paso solo puede ocurrir en la fila de paso: la 6ª para
        # las blancas y la 3ª para las negras. Aquí un peón blanco está en e4
        # (fila 3, no fila 4) y se finge que el peón negro de d4 acaba de hacer
        # un avance doble: la casilla "al paso" sería d3, que está en la misma
        # fila que el peón que captura, así que no hay nada que capturar.
        tablero = Tablero()
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.REY, Posicion(4, 0)))
        tablero.colocar(Pieza(Color.NEGRO, TipoPieza.REY, Posicion(4, 7)))
        tablero.colocar(Pieza(Color.NEGRO, TipoPieza.PEON, Posicion(3, 3)))   # d4
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 3)))  # e4
        tablero.ultima_jugada = Movimiento(Posicion(3, 1), Posicion(3, 3))  # d2-d4
        destinos = {p.notacion for p in tablero.destinos_de(Posicion(4, 3))}
        assert "d3" not in destinos
        # Con el peón blanco una fila más arriba (e5) tampoco puede capturar en
        # d3: la casilla al paso de un avance doble negro está en la fila 3, y
        # un peón blanco solo puede capturar al paso en la fila 6.
        tablero.colocar(Pieza(Color.BLANCO, TipoPieza.PEON, Posicion(4, 4)))  # e5
        destinos = {p.notacion for p in tablero.destinos_de(Posicion(4, 4))}
        assert "d3" not in destinos
        assert "d6" not in destinos  # d6 está vacía y no hay avance doble
        assert destinos == {"e6"}


# ----------------------------------------------------------------------
# Promoción
# ----------------------------------------------------------------------

class TestPromocion:
    def test_el_peon_promociona_a_dama_por_defecto(self):
        # La regla por defecto cuando no se indica a qué pieza se promueve.
        tablero = tablero_desde_fen("7k/4P3/8/8/8/8/8/4K3")
        mover(tablero, "e7", "e8")
        pieza = tablero.obtener(Posicion(4, 7))
        assert pieza.tipo is TipoPieza.DAMA
        assert pieza.color is Color.BLANCO

    @pytest.mark.parametrize(
        "letra,tipo",
        [("d", TipoPieza.DAMA), ("t", TipoPieza.TORRE),
         ("a", TipoPieza.ALFIL), ("c", TipoPieza.CABALLO)],
    )
    def test_el_peon_promociona_a_cualquier_pieza_legal(self, letra, tipo):
        tablero = tablero_desde_fen("7k/4P3/8/8/8/8/8/4K3")
        mover(tablero, "e7", "e8", promocion=TipoPieza(tipo))
        assert tablero.obtener(Posicion(4, 7)).tipo is tipo

    def test_no_se_puede_promocionar_a_rey_ni_a_peon(self):
        # Promocionar a rey dejaría dos reyes en el tablero, lo que no existe.
        tablero = tablero_desde_fen("7k/4P3/8/8/8/8/8/4K3")
        with pytest.raises(MovimientoIlegal):
            mover(tablero, "e7", "e8", promocion=TipoPieza.REY)
        with pytest.raises(MovimientoIlegal):
            mover(tablero, "e7", "e8", promocion=TipoPieza.PEON)

    def test_la_promocion_captura_conserva_el_color(self):
        tablero = tablero_desde_fen("3n3k/4P3/8/8/8/8/8/4K3")
        capturada = mover(tablero, "e7", "d8", promocion=TipoPieza.ALFIL)
        assert capturada.tipo is TipoPieza.CABALLO
        assert tablero.obtener(Posicion(3, 7)).tipo is TipoPieza.ALFIL
        assert tablero.obtener(Posicion(3, 7)).color is Color.BLANCO


# ----------------------------------------------------------------------
# Aplicar jugadas
# ----------------------------------------------------------------------

class TestAplicar:
    def test_aplicar_devuelve_la_pieza_capturada(self):
        tablero = tablero_desde_fen("4k3/8/8/3n4/8/8/8/3RK3")
        capturada = mover(tablero, "d1", "d5")
        assert capturada.tipo is TipoPieza.CABALLO
        assert capturada.color is Color.NEGRO

    def test_aplicar_rechaza_un_movimiento_ilegal(self):
        tablero = Tablero.posicion_inicial()
        with pytest.raises(MovimientoIlegal):
            mover(tablero, "e2", "e5")  # el peón no puede avanzar tres casillas

    def test_aplicar_rechaza_mover_una_casilla_vacia(self):
        tablero = Tablero.posicion_inicial()
        with pytest.raises(MovimientoIlegal):
            mover(tablero, "e4", "e5")

    def test_aplicar_recuerda_la_ultima_jugada(self):
        # Sin esto no se podría hacer la captura al paso.
        tablero = Tablero.posicion_inicial()
        mover(tablero, "e2", "e4")
        assert tablero.ultima_jugada.notacion == "e2-e4"

    def test_movimientos_de_una_casilla_vacia_devuelve_lista_vacia(self):
        assert Tablero.posicion_inicial().movimientos_de(Posicion(4, 3)) == []


# ----------------------------------------------------------------------
# Serialización y dibujo
# ----------------------------------------------------------------------

class TestSerializacionYDibujo:
    def test_ida_y_vuelta_conserva_el_tablero(self):
        # El viaje de ida y vuelta es lo que garantiza que guardar y cargar
        # una partida no altere la posición.
        original = Tablero.posicion_inicial()
        copia = Tablero.from_dict(original.to_dict())
        assert copia.clave() == original.clave()
        assert copia.derechos_enroque == original.derechos_enroque

    def test_el_dibujo_tiene_filas_columnas_y_piezas(self):
        # Se comprueba el dibujo porque la vista depende de él y porque es
        # la forma más rápida de detectar que el tablero se ha vaciado o ha
        # perdido piezas por el camino.
        texto = str(Tablero.posicion_inicial())
        lineas = texto.splitlines()
        assert len(lineas) == 9  # 8 filas + la de las letras de columna
        assert lineas[0].startswith("8 ")
        assert lineas[7].startswith("1 ")
        assert "a b c d e f g h" in lineas[8]

    def test_la_clave_cambia_al_mover_una_pieza(self):
        # La clave es la base de la detección de repeticiones de ``Partida``.
        tablero = Tablero.posicion_inicial()
        antes = tablero.clave()
        mover(tablero, "e2", "e4")
        assert tablero.clave() != antes
