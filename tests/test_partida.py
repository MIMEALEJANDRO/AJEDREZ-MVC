"""Pruebas de ``Partida``: turnos, jugadas, fines de partida y persistencia.

``Tablero`` ya sabe qué es legal; aquí se comprueba lo que solo existe cuando
hay *historia*: el turno que alterna, el jaque mate, el ahogado, las tablas, la
pérdida de los derechos de enroque y el FEN completo.

Las posiciones de mate y ahogado que se usan son posiciónes de taller, mínimas:
se quitan todas las piezas que sobran porque así el problema se lee de un
vistazo y el fallo (si lo hay) está en la regla y no en el ruido de la posición.
"""

import pytest

from models.enums import Color, EstadoPartida, TipoPieza
from models.errores import ErrorAjedrez, MovimientoIlegal, PartidaTerminada
from models.partida import Partida
from models.posicion import Posicion
from models.tablero import Tablero

INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


# ----------------------------------------------------------------------
# Partida nueva y turnos
# ----------------------------------------------------------------------

class TestTurnos:
    def test_una_partida_nueva_empieza_con_las_blancas(self):
        partida = Partida()
        assert partida.turno is Color.BLANCO
        assert partida.estado is EstadoPartida.EN_CURSO
        assert partida.historial == []
        assert len(partida.tablero.piezas()) == 32

    def test_el_turno_alterna_despues_de_cada_jugada(self):
        partida = Partida()
        partida.mover("e2", "e4")
        assert partida.turno is Color.NEGRO
        partida.mover("e7", "e5")
        assert partida.turno is Color.BLANCO

    def test_no_se_puede_jugar_con_el_color_contrario(self):
        # Es la regla más básica del juego y la que más se olvida al
        # implementar. Aquí la comprueba ``mover``.
        #
        # Tras 1.e4 es el turno de las negras, así que la jugada prohibida es
        # la de una pieza **blanca** (d2). Con una pieza negra sería legal.
        partida = Partida()
        partida.mover("e2", "e4")
        with pytest.raises(MovimientoIlegal):
            partida.mover("d2", "d4")

    def test_el_numero_de_jugada_sube_con_cada_jugada_de_las_negras(self):
        partida = Partida()
        assert partida.numero_movimiento == 1
        partida.mover("e2", "e4")
        assert partida.numero_movimiento == 1
        partida.mover("e7", "e5")
        assert partida.numero_movimiento == 2

    def test_mover_devuelve_el_movimiento_realizado(self):
        movimiento = Partida().mover("e2", "e4")
        assert movimiento.notacion == "e2-e4"

    def test_acepta_posiciones_como_objetos_y_como_texto(self):
        # El mismo método se usa desde la consola (texto) y desde el código
        # (objetos), así que tiene que aceptar las dos formas.
        partida = Partida()
        partida.mover(Posicion.desde_notacion("e2"), Posicion.desde_notacion("e4"))
        assert partida.historial[0].notacion == "e2-e4"

    def test_movimientos_disponibles_son_los_del_turno(self):
        partida = Partida()
        assert len(partida.movimientos_disponibles()) == 20
        partida.mover("e2", "e4")
        assert len(partida.movimientos_disponibles()) == 20


# ----------------------------------------------------------------------
# Jaque mate y ahogado
# ----------------------------------------------------------------------

class TestJaqueMate:
    # Mate del pasillo (mate del pasillo de rey y dama). No hay escapatoria:
    # el rey no tiene casillas a las que ir y nada puede capturar a la dama.
    MATE_EN_UNA = "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"

    def test_detecta_el_jaque_mate(self):
        partida = Partida.desde_fen(self.MATE_EN_UNA)
        partida.mover("a1", "a8")
        assert partida.estado is EstadoPartida.JAQUE_MATE
        assert partida.ganador is Color.BLANCO
        assert "jaque mate" in partida.motivo

    def test_una_partida_terminada_no_acepta_mas_jugadas(self):
        partida = Partida.desde_fen(self.MATE_EN_UNA)
        partida.mover("a1", "a8")
        with pytest.raises(PartidaTerminada):
            partida.mover("g8", "g7")

    def test_reiniciar_devuelve_la_partida_al_estado_inicial(self):
        # Se comprueba con todos los atributos que una partida puede tener
        # tocados, porque el error típico es reiniciar el tablero y olvidar
        # el turno o el historial.
        partida = Partida.desde_fen(self.MATE_EN_UNA)
        partida.mover("a1", "a8")
        partida.reiniciar()
        assert partida.turno is Color.BLANCO
        assert partida.estado is EstadoPartida.EN_CURSO
        assert partida.ganador is None
        assert partida.motivo == ""
        assert partida.historial == []
        assert partida.semicontador == 0
        assert partida.numero_movimiento == 1
        assert len(partida.tablero.piezas()) == 32

    def test_estado_deja_de_terminada_al_reiniciar(self):
        partida = Partida()
        partida.abandonar()
        assert partida.esta_terminada() is True
        partida.reiniciar()
        assert partida.esta_terminada() is False

    def test_abandonar_da_la_victoria_al_contrario(self):
        partida = Partida()
        partida.abandonar()
        assert partida.estado is EstadoPartida.ABANDONO
        assert partida.ganador is Color.NEGRO
        assert "abandonaron" in partida.motivo

    def test_no_se_puede_abandonar_dos_veces(self):
        partida = Partida()
        partida.abandonar()
        with pytest.raises(PartidaTerminada):
            partida.abandonar()


class TestAhogado:
    # Rey negro acorralado por su propio rey blanco: sin jaque, sin salida.
    AHOGADO = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"

    def test_detecta_el_ahogado(self):
        partida = Partida.desde_fen(self.AHOGADO)
        # No hace falta jugar nada: la posición ya está ahogada y se detecta
        # al cargarla. Por eso ``desde_fen`` recalcula el estado.
        assert partida.estado is EstadoPartida.AHOGADO
        assert partida.ganador is None

    def test_el_ahogado_no_tiene_ganador(self):
        partida = Partida.desde_fen(self.AHOGADO)
        assert partida.ganador is None
        assert "ahogado" in partida.motivo

    def test_el_ahogado_tambien_es_una_partida_terminada(self):
        partida = Partida.desde_fen(self.AHOGADO)
        with pytest.raises(PartidaTerminada):
            partida.mover("h8", "h7")


# ----------------------------------------------------------------------
# Tablas
# ----------------------------------------------------------------------

class TestTablas:
    def test_material_insuficiente_solo_con_reyes(self):
        partida = Partida.desde_fen("8/8/4k3/8/8/4K3/8/8 w - - 0 1")
        assert partida.estado is EstadoPartida.TABLAS
        assert partida.ganador is None
        assert "material" in partida.motivo

    def test_material_insuficiente_con_un_solo_alfil(self):
        partida = Partida.desde_fen("8/8/4k3/8/8/4K3/8/5B2 w - - 0 1")
        assert partida.estado is EstadoPartida.TABLAS

    def test_material_insuficiente_con_dos_alfiles_en_el_mismo_color(self):
        # Los dos alfiles en casillas del mismo color nunca pueden cooperar
        # para dar mate. En la primera fila las casillas claras son b1, d1, f1
        # y h1, así que los alfiles van en b1 y f1.
        partida = Partida.desde_fen("8/8/4k3/8/8/4K3/8/1B2KB2 w - - 0 1")
        assert partida.estado is EstadoPartida.TABLAS

    def test_dos_alfiles_en_casillas_distintas_no_son_tablas(self):
        # Este sí puede dar mate, así que la partida sigue en curso: b1 es clara
        # y g1 es oscura.
        partida = Partida.desde_fen("8/8/4k3/8/8/4K3/8/1B2K1B1 w - - 0 1")
        assert partida.estado is EstadoPartida.EN_CURSO

    def test_no_es_material_insuficiente_con_un_caballo_y_un_alfil(self):
        # Con más de una pieza, salvo el caso de los alfiles, siempre se puede
        # llegar a un mate.
        partida = Partida.desde_fen("8/8/4k3/8/8/4K3/8/3B1N2 w - - 0 1")
        assert partida.estado is EstadoPartida.EN_CURSO

    def test_la_regla_de_las_50_jugadas(self):
        # Se partie de una posición sin peones y se hacen jugadas de torre y
        # rey que no se capturen. Es imposible jugarlas todas a mano en una
        # prueba, así que se comprueba directamente el contador, que es lo que
        # dispara la regla.
        partida = Partida.desde_fen("8/8/4k3/8/8/4K3/8/R6R w - - 98 60")
        partida.semicontador = 99
        partida.mover("a1", "a2")
        assert partida.semicontador == 100
        partida.recalcular_estado()
        assert partida.estado is EstadoPartida.TABLAS
        assert "50 jugadas" in partida.motivo

    def test_una_captura_reinicia_el_contador_de_las_50_jugadas(self):
        # Torre blanca en g1 y peón negro en g2: al capturar, el contador vuelve
        # a cero aunque llevara 40 medias jugadas sin nada.
        partida = Partida.desde_fen("8/8/4k3/8/8/8/6p1/R4KR1 w - - 10 20")
        partida.semicontador = 40
        partida.mover("g1", "g2")  # la torre captura el peón: contador a cero
        assert partida.semicontador == 0

    def test_el_movimiento_de_un_peon_tambien_reinicia_el_contador(self):
        partida = Partida()
        partida.semicontador = 40
        partida.mover("e2", "e4")
        assert partida.semicontador == 0

    def test_las_tablas_por_repeticion(self):
        # Se repite tres veces una posición con solo reyes, torres y caballos.
        #
        # Se mueven los caballos y no los reyes ni las torres porque los
        # derechos de enroque también forman parte de la posición: si se moviera
        # una torre, al volver a la posición inicial el tablero sería el mismo
        # pero faltarían derechos, y según el reglamento no sería la misma
        # posición.
        partida = Partida.desde_fen("4k1n1/8/8/8/8/8/8/RN2K2R w KQ - 0 1")
        for _ in range(2):
            partida.mover("b1", "c3")
            partida.mover("g8", "f6")
            partida.mover("c3", "b1")
            partida.mover("f6", "g8")
        # Tras dos vueltas completas la posición inicial ha aparecido 3 veces
        # (una al cargar y dos al volver), así que son tablas.
        assert partida.estado is EstadoPartida.TABLAS
        assert "repitió" in partida.motivo

    def test_perder_un_derecho_de_enroque_impide_declarar_tablas_por_repeticion(self):
        # El caso contrario del anterior, y el motivo de que los derechos
        # entren en la clave: se vuelve a la posición inicial, pero sin el
        # derecho a enroque por el lado de la dama, así que no es repetición.
        partida = Partida.desde_fen("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        for _ in range(2):
            partida.mover("a1", "a2")
            partida.mover("e8", "e7")
            partida.mover("a2", "a1")
            partida.mover("e7", "e8")
        assert partida.estado is EstadoPartida.EN_CURSO


# ----------------------------------------------------------------------
# Derechos de enroque
# ----------------------------------------------------------------------

class TestDerechosDeEnroque:
    def test_mover_el_rey_pierde_los_dos_derechos(self):
        # Se juega con una posición sin peones ni alfil en f1, para que el rey
        # pueda moverse de verdad a f1 (en la posición inicial el alfil ocupa
        # esa casilla y e1-f1 sería una jugada ilegal, no una jugada de rey).
        partida = Partida.desde_fen("4k3/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        partida.mover("e1", "f1")
        assert partida.tablero.derechos_enroque == {"k", "q"}

    def test_mover_una_torre_pierde_su_derecho(self):
        # Mismo motivo: el caballo de g1 ocupa la casilla de salida de la torre.
        partida = Partida.desde_fen("4k3/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        partida.mover("h1", "g1")
        assert partida.tablero.derechos_enroque == {"Q", "k", "q"}

    def test_capturar_una_torre_en_su_casilla_pierde_el_derecho(self):
        # Se prepara una posición donde las blancas pueden capturar la torre
        # negra de h8.
        partida = Partida.desde_fen("r3k2r/7R/8/8/8/8/8/4K3 w kq - 0 1")
        partida.mover("h7", "h8")
        assert "k" not in partida.tablero.derechos_enroque

    def test_la_torre_que_vuelve_no_recupera_el_derecho(self):
        # El derecho se pierde para siempre: no depende de dónde esté la
        # torre ahora, sino de que se movió alguna vez.
        partida = Partida.desde_fen("4k3/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        partida.mover("h1", "g1")
        partida.mover("e8", "e7")
        partida.mover("g1", "h1")
        partida.mover("e7", "e8")
        assert "K" not in partida.tablero.derechos_enroque

    def test_los_derechos_se_reflejan_en_el_fen(self):
        partida = Partida()
        assert partida.a_fen() == INICIAL
        partida.mover("e2", "e4")
        # Al mover el peón no se pierden derechos, pero sí al mover el rey.
        partida.mover("e7", "e5")
        partida.mover("e1", "e2")
        assert partida.a_fen().split(" ")[2] == "kq"


# ----------------------------------------------------------------------
# FEN
# ----------------------------------------------------------------------

class TestFen:
    def test_el_fen_de_la_posicion_inicial_es_el_estandar(self):
        # Este es el FEN que usan todos los programas de ajedrez. Si difiere,
        # la partida no se podría abrir en ningún otro sitio.
        assert Partida().a_fen() == INICIAL

    def test_ida_y_vuelta_por_fen(self):
        # La propiedad importante: cargar un FEN y volver a escribirlo tiene
        # que dar exactamente lo mismo. Es lo que permite recargar un FEN
        # guardado sin que se degrade poco a poco.
        partida = Partida()
        partida.mover("e2", "e4")
        partida.mover("c7", "c5")
        partida.mover("g1", "f3")
        partida.mover("d7", "d6")
        fen = partida.a_fen()
        assert Partida.desde_fen(fen).a_fen() == fen

    def test_el_fen_anota_el_turno(self):
        partida = Partida()
        partida.mover("e2", "e4")
        assert partida.a_fen().split(" ")[1] == "b"

    def test_el_fen_anota_la_casilla_al_paso(self):
        partida = Partida()
        partida.mover("e2", "e4")
        # Tras un avance doble de peón, la casilla "al paso" es la intermedia.
        assert partida.a_fen().split(" ")[3] == "e3"
        partida.mover("e7", "e5")
        partida.mover("g1", "f3")
        # Una jugada que no es avance doble de peón deja el campo en "-".
        assert partida.a_fen().split(" ")[3] == "-"

    def test_el_fen_anota_el_contador_de_capturas(self):
        partida = Partida()
        partida.mover("e2", "e4")
        partida.mover("d7", "d5")
        partida.mover("e4", "d5")  # captura: el contador vuelve a 0
        assert partida.a_fen().split(" ")[4] == "0"

    def test_el_fen_anota_el_numero_de_jugada(self):
        partida = Partida()
        partida.mover("e2", "e4")
        partida.mover("e7", "e5")
        assert partida.a_fen().split(" ")[5] == "2"

    def test_los_derechos_de_enroque_se_escriben_en_orden_canonico(self):
        # KQkq y no el orden que devuelva `sorted`, para que el mismo tablero
        # produzca siempre el mismo texto.
        partida = Partida()
        partida.tablero.derechos_enroque = {"q", "K", "k", "Q"}
        assert partida.a_fen().split(" ")[2] == "KQkq"

    def test_sin_derechos_de_enroque_el_fen_pone_guion(self):
        partida = Partida()
        partida.tablero.derechos_enroque = set()
        assert partida.a_fen().split(" ")[2] == "-"

    def test_cargar_desde_fen_conserva_los_derechos_de_enroque(self):
        partida = Partida.desde_fen(INICIAL)
        assert partida.tablero.derechos_enroque == {"K", "Q", "k", "q"}

    def test_cargar_desde_fen_establece_el_turno(self):
        assert Partida.desde_fen(INICIAL).turno is Color.BLANCO
        assert Partida.desde_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1").turno is Color.NEGRO

    def test_cargar_desde_fen_reconstruye_la_captura_al_paso(self):
        # Este es el detalle que hace que un FEN "vale" como posición completa:
        # tras "e4" el campo al paso es e3, y al cargar hay que poder hacer
        # "dxe3" al paso.
        partida = Partida.desde_fen(INICIAL)
        partida.mover("e2", "e4")
        partida.mover("a7", "a5")
        partida.mover("e4", "e5")
        partida.mover("d7", "d5")
        recargada = Partida.desde_fen(partida.a_fen())
        assert not recargada.esta_terminada()
        recargada.mover("e5", "d6")
        assert recargada.tablero.obtener(Posicion.desde_notacion("d6")).tipo is TipoPieza.PEON

    @pytest.mark.parametrize(
        "fen",
        [
            "",                                        # vacío
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR x KQkq - 0 1",  # turno inválido
        ],
    )
    def test_rechaza_fens_invalidos(self, fen):
        with pytest.raises(ErrorAjedrez):
            Partida.desde_fen(fen)


# ----------------------------------------------------------------------
# Promoción desde la interfaz de la partida
# ----------------------------------------------------------------------

class TestPromocionDesdePartida:
    def test_se_puede_indicar_la_promocion_con_texto(self):
        partida = Partida.desde_fen("7k/4P3/8/8/8/8/8/4K3 w - - 0 1")
        partida.mover("e7", "e8", "torre")
        assert partida.tablero.obtener(Posicion(4, 7)).tipo is TipoPieza.TORRE

    def test_se_puede_indicar_la_promocion_con_la_letra_de_fen(self):
        partida = Partida.desde_fen("7k/4P3/8/8/8/8/8/4K3 w - - 0 1")
        partida.mover("e7", "e8", "a")
        assert partida.tablero.obtener(Posicion(4, 7)).tipo is TipoPieza.ALFIL

    def test_una_promocion_desconocida_da_error(self):
        partida = Partida.desde_fen("7k/4P3/8/8/8/8/8/4K3 w - - 0 1")
        with pytest.raises(MovimientoIlegal):
            partida.mover("e7", "e8", "unicornio")

    def test_no_se_puede_promocionar_a_peon(self):
        partida = Partida.desde_fen("7k/4P3/8/8/8/8/8/4K3 w - - 0 1")
        with pytest.raises(MovimientoIlegal):
            partida.mover("e7", "e8", "peon")


# ----------------------------------------------------------------------
# Historial, deshacer y clonar
# ----------------------------------------------------------------------

class TestHistorial:
    def test_cada_jugada_se_añade_al_historial(self):
        partida = Partida()
        partida.mover("e2", "e4")
        partida.mover("e7", "e5")
        assert [m.notacion for m in partida.historial] == ["e2-e4", "e7-e5"]

    def test_la_notacion_agrupa_las_jugadas_por_numeracion(self):
        partida = Partida()
        partida.mover("e2", "e4")
        partida.mover("e7", "e5")
        partida.mover("g1", "f3")
        assert partida.jugadas_en_notacion() == ["1. e2-e4 e7-e5", "2. g1-f3"]

    def test_deshacer_revierte_la_ultima_jugada(self):
        partida = Partida()
        partida.mover("e2", "e4")
        partida.mover("e7", "e5")
        deshecho = partida.deshacer()
        assert deshecho.notacion == "e7-e5"
        assert partida.turno is Color.NEGRO
        assert len(partida.historial) == 1
        # Y el tablero vuelve a estar como estaba.
        assert partida.tablero.en_juego(Posicion.desde_notacion("e7"))
        assert not partida.tablero.en_juego(Posicion.desde_notacion("e5"))

    def test_deshacer_sin_jugadas_no_falla(self):
        partida = Partida()
        assert partida.deshacer() is None

    def test_deshacer_varias_veces_deja_la_partida_jugable(self):
        # Tras deshacer, la partida no puede quedar en un estado raro (por
        # ejemplo, con el tablero movido y el historial sin la jugada que lo
        # movió), porque eso rompería la partida para siempre.
        partida = Partida()
        partida.mover("e2", "e4")
        partida.mover("e7", "e5")
        partida.mover("g1", "f3")
        partida.deshacer()
        partida.deshacer()
        # Tras deshacer dos de las tres jugadas queda solo 1.e4 y vuelve a tocar
        # a las negras, así que la jugada que demuestra que la partida sigue
        # viva tiene que ser negra.
        partida.mover("e7", "e6")
        assert partida.turno is Color.BLANCO
        assert len(partida.historial) == 2

    def test_clonar_produce_una_partida_independiente(self):
        # La copia se usa para deshacer y para probar jugadas: si compartiera
        # estado con el original, mover en una movería en la otra.
        partida = Partida()
        partida.mover("e2", "e4")
        copia = partida.clonar()
        copia.mover("e7", "e5")
        assert len(copia.historial) == 2
        assert len(partida.historial) == 1
        assert partida.turno is Color.NEGRO


# ----------------------------------------------------------------------
# Persistencia de la partida
# ----------------------------------------------------------------------

class TestSerializacionDePartida:
    def test_ida_y_vuelta_conserva_el_estado(self):
        # Esta prueba es la que garantiza que guardar y cargar funciona. Se
        # comprueba atributo por atributo, porque un campo olvidado (el turno,
        # el estado) produciría partidas corruptas al cargarlas.
        # La posición lleva peones, porque 1.e4 y 1...e5 son jugadas de peón:
        # en un tablero de solo reyes y torres no existirían.
        partida = Partida.desde_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 3 12")
        partida.mover("e2", "e4")
        partida.mover("e7", "e5")

        copia = Partida.from_dict(partida.to_dict())
        assert copia.turno is partida.turno
        assert copia.estado is partida.estado
        assert copia.ganador is partida.ganador
        assert copia.semicontador == partida.semicontador
        assert copia.numero_movimiento == partida.numero_movimiento
        assert copia.tablero.clave() == partida.tablero.clave()
        assert copia.tablero.derechos_enroque == partida.tablero.derechos_enroque
        assert [m.notacion for m in copia.historial] == [
            m.notacion for m in partida.historial
        ]

    def test_conserva_el_fen_exacto(self):
        # Si el viaje de ida y vuelta por diccionario y el viaje por FEN dan el
        # mismo texto, ambas formas de persistir son equivalentes.
        partida = Partida()
        partida.mover("e2", "e4")
        partida.mover("c7", "c5")
        partida.mover("g1", "f3")
        copia = Partida.from_dict(partida.to_dict())
        assert copia.a_fen() == partida.a_fen()

    def test_conserva_una_partida_terminada(self):
        partida = Partida()
        partida.abandonar()
        copia = Partida.from_dict(partida.to_dict())
        assert copia.estado is EstadoPartida.ABANDONO
        assert copia.ganador is Color.NEGRO
        assert copia.motivo == partida.motivo

    def test_conserva_el_estado_de_jaque_mate(self):
        partida = Partida.desde_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        partida.mover("a1", "a8")
        copia = Partida.from_dict(partida.to_dict())
        assert copia.estado is EstadoPartida.JAQUE_MATE
        assert copia.esta_terminada() is True

    def test_rechaza_datos_invalidos(self):
        # Si alguien edita el JSON a mano y escribe un color que no existe, el
        # error tiene que saltar al cargar, no dos horas después en una jugada.
        datos = Partida().to_dict()
        datos["turno"] = "azul"
        with pytest.raises(ValueError):
            Partida.from_dict(datos)

    def test_el_tablero_tambien_hace_ida_y_vuelta(self):
        # Prueba de una línea para confirmar que el diccionario que genera
        # ``Tablero.to_dict`` es el que espera ``from_dict`` (incluida la
        # última jugada, que es lo que permite la captura al paso).
        partida = Partida()
        partida.mover("e2", "e4")
        copia = Partida.from_dict(partida.to_dict())
        assert copia.tablero.ultima_jugada is not None
        assert copia.tablero.ultima_jugada.notacion == "e2-e4"


# ----------------------------------------------------------------------
# Presentación
# ----------------------------------------------------------------------

class TestPresentacion:
    def test_el_resumen_dice_de_quien_es_el_turno(self):
        partida = Partida()
        assert "blancas" in partida.resumen()
        partida.mover("e2", "e4")
        assert "negras" in partida.resumen()

    def test_el_resumen_avisa_del_jaque(self):
        partida = Partida.desde_fen("4k3/8/8/8/8/8/4R3/4K3 b - - 0 1")
        assert "jaque" in partida.resumen()

    def test_el_resumen_de_una_partida_terminada_dice_el_motivo(self):
        partida = Partida()
        partida.abandonar()
        resumen = partida.resumen()
        assert "Abandono" in resumen
        # Quien abandona son las blancas, así que ganan las negras.
        assert "negras" in resumen
        assert "Las blancas abandonaron" in resumen

    def test_str_muestra_el_tablero_y_el_resumen(self):
        texto = str(Partida())
        assert "♔" in texto   # el rey blanco
        assert "Turno de las blancas" in texto
