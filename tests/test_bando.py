"""Pruebas del bando: con quién se juega y a quién le toca empezar.

Estas pruebas son las que destaparon un bloque de la ventana jugable, y son las
que lo evitan en adelante. El síntoma era este: al elegir "Negras" en el selector
del panel lateral, el tablero se giraba (la vista estaba bien) pero la partida se
quedaba **bloqueada**: no se podía mover ninguna pieza.

Por qué se quedaba bloqueada, que es lo que las pruebas fijan: el controlador
comprueba el turno antes de aplicar una jugada, y se compara contra
``color_jugador``. Al elegir negras, ``color_jugador``.passaba a ser negro pero la
partida seguía con ``turno`` en blanco (porque ``Partida.reiniciar()`` siempre
empieza con las blancas). Las dos comprobaciones de la ventana se/entra en
piezas del color elegido. Resultado: ninguna jugada era legal, ni de las negras
(turno de las blancas) ni de las blancas (no es tu bando).

Aquí no hay pantalla ni ``tkinter``: lo que se comprueba es el turno, que es lo
que estaba mal, y vive en el controlador. Lo que sí depende de la ventana (que el
tablero se gire, que el botón llame al controlador) está en
``test_ventana_bando.py``, que sí necesita ``xvfb-run``.
"""

from __future__ import annotations

from controllers.partida_controller import PartidaController
from models.enums import Color
from storage.base_storage import BaseStorage


class StorageEnMemoria(BaseStorage):
    """Almacenamiento que no toca el disco. Da igual cuál sea la partida."""

    def __init__(self) -> None:
        self.guardadas: dict[str, object] = {}

    def _leer_todas(self) -> dict:
        return {}

    def _escribir_todas(self, partidas: dict) -> None:
        self.guardadas = dict(partidas)

    def _ordenar_claves(self, claves: list[str]) -> list[str]:
        return sorted(claves, reverse=True)

    def listar_informes(self) -> list[dict]:
        return []


class VistaMinima:
    """Los cuatro métodos que el controlador usa de verdad, y nada más.

    ``elegir_color`` no pregunta nada: devuelve el color que ya esté elegido en el
    panel. Es lo mismo que hace ``SalidaDeConsola`` en la ventana jugable, y por
    eso el doble reproduce el caso real en vez de un caso ideal.
    """

    def __init__(self, color: Color | None) -> None:
        self.color = color
        self.mensajes: list[str] = []

    def elegir_color(self) -> Color | None:
        return self.color

    def mostrar_mensaje(self, mensaje: str) -> None:
        self.mensajes.append(mensaje)

    def mostrar_error(self, error) -> None:
        self.mensajes.append(str(error))

    def escribir(self, texto: str = "") -> None:
        pass

    def titulo(self, texto: str) -> None:
        pass

    def pedir_confirmacion(self, pregunta: str) -> bool:
        return True


def controlador_con(color: Color | None) -> PartidaController:
    return PartidaController(vista=VistaMinima(color), storage=StorageEnMemoria())


# ---------------------------------------------------------------------------
# Quién empieza
# ---------------------------------------------------------------------------

class TestQuienEmpieza:
    def test_con_blancas_mueven_las_blancas(self):
        control = controlador_con(Color.BLANCO)
        control.nueva_partida()
        assert control.partida.turno is Color.BLANCO
        assert control.aplicar_jugada("e2e4") is True

    def test_con_negras_mueven_las_negras(self):
        # Este es el test que falla antes del arreglo. Elegir negras y que la
        # partida empiece con las blancas hacía la partida injugable.
        control = controlador_con(Color.NEGRO)
        control.nueva_partida()
        assert control.partida.turno is Color.NEGRO
        assert control.aplicar_jugada("e7e5") is True

    def test_con_los_dos_colores_mueven_las_blancas(self):
        # "Los dos colores" no es un bando: no hay nadie a quien dar la primera
        # jugada, así que se empieza como siempre, con las blancas.
        control = controlador_con(None)
        control.nueva_partida()
        assert control.partida.turno is Color.BLANCO
        assert control.aplicar_jugada("e2e4") is True

    def test_el_color_se_puede_elegir_al_arrancar_y_al_reiniciar(self):
        # Elegir el bando y reiniciar tienen que dejar el turno en el mismo sitio,
        # o reiniciar dejaría la partida a medias de un bando con el otro.
        control = controlador_con(Color.NEGRO)
        control.nueva_partida()
        control.aplicar_jugada("e7e5")
        control.nueva_partida()
        assert control.partida.turno is Color.NEGRO
        assert control.aplicar_jugada("e7e5") is True


# ---------------------------------------------------------------------------
# Consistencia del turno una vez empezada
# ---------------------------------------------------------------------------

class TestConsistenciaDelTurno:
    def test_mover_el_color_contrario_se_rechaza_en_capa_de_modelo(self):
        # Con negras y con el turno de las negras, mover un peón blanco lo
        # rechaza el **modelo** (a quién le toca), no el filtro de bando del
        # controlador. Los dos rechazos existen y son cosas distintas: por eso
        # aquí se comprueba que el turno es el de las negras y que la jugada se
        # rechaza, sin mirar el texto exacto del mensaje.
        control = controlador_con(Color.NEGRO)
        control.nueva_partida()
        assert control.partida.turno is Color.NEGRO
        assert control.aplicar_jugada("e2e4") is False
        assert control.partida.historial == []

    def test_mover_su_propio_color_fuera_de_turno_se_rechaza_en_el_controlador(self):
        # El otro rechazo: ya han movido las negras, le toca a las blancas, y el
        # jugador con bando negro no puede. Aquí el aviso sí es del
        # controlador, y se comprueba el texto porque es el que ve la persona.
        control = controlador_con(Color.NEGRO)
        control.nueva_partida()
        assert control.aplicar_jugada("e7e5") is True
        assert control.aplicar_jugada("g8f6") is False
        assert any(
            "no es su turno" in m.lower() for m in control.vista.mensajes
        ), control.vista.mensajes

    def test_los_turnos_alternan_en_la_partida(self):
        # Con "los dos colores" se juega la partida entera, así que aquí sí se
        # pueden jugar las dos partes. Lo que se comprueba es que el turno
        # alterna como en el ajedrez, una jugada de cada color.
        control = controlador_con(None)
        control.nueva_partida()
        for jugada in ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"):
            assert control.aplicar_jugada(jugada) is True, jugada
        assert control.partida.turno is Color.BLANCO
        assert len(control.partida.historial) == 6

    def test_con_un_solo_bando_solo_se_juega_esa_parte(self):
        # Documenta el límite del modo "un solo color" sin rival: se puede
        # mover ese bando cuando le toca, y el turno se le escapa después. Es el
        # comportamiento que había antes de este arreglo (con la diferencia de
        # que ahora la primera jugada sí se puede hacer) y está anotado en el
        # README. Ver también ``test_el_turno_se_conserva_al_guardar_y_cargar``.
        control = controlador_con(Color.NEGRO)
        control.nueva_partida()
        assert control.aplicar_jugada("e7e5") is True
        assert control.aplicar_jugada("g8f6") is False
        assert len(control.partida.historial) == 1
        assert control.partida.turno is Color.BLANCO

    def test_el_turno_se_conserva_al_guardar_y_cargar(self):
        # Guardar y recargar no puede cambiar a quién le toca. Con negras, tras
        # su primera jugada el turno es del otro bando: eso es la regla del
        # ajedrez y la aplicación la respeta, así que quien juegue un solo color
        # solo puede hacer una de cada dos jugadas. Se fija aquí para que quede
        # escrito; ver el aviso del README sobre el bando único.
        control = controlador_con(Color.NEGRO)
        control.nueva_partida()
        control.aplicar_jugada("e7e5")
        clave = control.guardar("con negras")

        recargado = PartidaController(vista=VistaMinima(Color.NEGRO), storage=control.storage)
        recargado.cargar(clave)
        recargado.color_jugador = Color.NEGRO
        # El turno sigue siendo el que era: ahora el de las blancas.
        assert recargado.partida.turno is Color.BLANCO
        # Y por eso la jugada de las blancas se rechaza con el aviso de turno.
        assert recargado.aplicar_jugada("e2e4") is False
        assert any("no es su turno" in m.lower() for m in recargado.vista.mensajes)

    def test_con_los_dos_colores_se_pueden_jugar_las_dos_partidas(self):
        # El modo "los dos colores" es el que permite practicar solo: sin bando
        # no hay a quién negarle el turno, así que se juega la partida entera.
        control = controlador_con(None)
        control.nueva_partida()
        for jugada in ("e2e4", "e7e5", "g1f3", "b8c6"):
            assert control.aplicar_jugada(jugada) is True, jugada
