"""Pruebas del bando: quién puede mover, y por qué.

Estas pruebas fijan la regla que se decidió para el modo de un solo jugador:

* **Siempre empiezan las blancas.** No es una preferencia, es el reglamento, y
  por eso está en ``Partida.reiniciar`` y no como parámetro.
* **Con un bando elegido solo se mueve la jugada de ese bando.** Con Blancas se
  juega ``e2e4`` y ahí se acaba el turno de la persona; con Negras no se puede
  mover nada, porque mueven las blancas.
* **Con "los dos colores" se juega la partida entera**, porque no hay bando que
  esperar. Es el único modo que permite practicar de principio a fin.

No hay pantalla ni ``tkinter`` aquí: lo que se comprueba es quién puede mover, y
eso vive en el controlador. Lo que depende de la ventana (que el tablero se gire,
que el botón del panel de FEN) está en ``test_ventana.py``, que sí necesita
``xvfb-run``.

De dónde sale la regla
---------------------
``PartidaController.color_que_juega`` es el único sitio que decide quién mueve.
Que haya **uno solo** es lo importante: antes la misma pregunta estaba
repetida en tres puntos distintos de la ventana (pintar el tablero atenuado,
aceptar un clic, y el aviso de "no es su turno"), y por eso un cambio de bando
podía dejar el tablero diciendo una cosa y los clics otra.
"""

from __future__ import annotations

from controllers.partida_controller import PartidaController
from models.enums import Color
from models.posicion import Posicion
from storage.base_storage import BaseStorage


class StorageEnMemoria(BaseStorage):
    """Almacenamiento que no toca el disco."""

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
    """Los métodos que el controlador usa de verdad, y nada más.

    ``elegir_color`` no pregunta: devuelve el bando ya elegido, igual que hace
    ``SalidaDeConsola`` en la ventana jugable.
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
    control = PartidaController(vista=VistaMinima(color), storage=StorageEnMemoria())
    control.nueva_partida(color)
    return control


# ---------------------------------------------------------------------------
# La regla del turno inicial
# ---------------------------------------------------------------------------

class TestTurnoInicial:
    def test_siempre_empiezan_las_blancas(self):
        # Los tres bandos, y siempre las blancas. Es la regla del reglamento y
        # por eso ``Partida.reiniciar`` no admite otro turno.
        for color in (Color.BLANCO, Color.NEGRO, None):
            control = controlador_con(color)
            assert control.partida.turno is Color.BLANCO, color

    def test_reiniciar_no_tiene_turno_que_elegir(self):
        # La firma lo dice: si alguien intenta pasar un turno, revienta. Es
        # mejor que un reiniciar(turno=NEGRO) que nadie espera.
        import inspect

        from models.partida import Partida

        assert list(inspect.signature(Partida.reiniciar).parameters) == ["self"]
        assert list(inspect.signature(PartidaController.nueva_partida).parameters) == [
            "self",
            "color",
        ]

    def test_el_bando_no_cambia_el_turno_al_reiniciar(self):
        # El bando se guarda, el turno no se toca: reiniciar con cualquier bando
        # devuelve siempre la misma posición inicial con las blancas al frente.
        for color in (Color.NEGRO, Color.BLANCO, None):
            control = controlador_con(color)
            control.nueva_partida(color)
            assert control.partida.turno is Color.BLANCO, color


# ---------------------------------------------------------------------------
# Quién puede mover
# ---------------------------------------------------------------------------

class TestQuienPuedeMover:
    def test_con_blancas_se_puede_mover_la_primera_jugada(self):
        # Es el caso bueno: se elige Blancas, mueven las blancas y se puede hacer
        # la jugada. Es lo que pasa al abrir el programa.
        control = controlador_con(Color.BLANCO)
        assert control.color_que_juega() is Color.BLANCO
        assert control.aplicar_jugada("e2e4") is True

    def test_con_blancas_despues_de_mover_no_se_puede_mas(self):
        # El límite del modo de un jugador: tras tu jugada el turno es del otro
        # bando y no puedes mover hasta que ese bando mueva. Con rival esto se
        # resuelve solo; sin rival, se juega con "los dos colores".
        control = controlador_con(Color.BLANCO)
        control.aplicar_jugada("e2e4")
        assert control.color_que_juega() is None
        assert control.aplicar_jugada("e7e5") is False
        assert any("no es su turno" in m.lower() for m in control.vista.mensajes)

    def test_con_negras_no_se_puede_mover_nada(self):
        # Elegir Negras con un solo jugador no deja jugar: mueven las blancas y
        # no hay nadie que las mueva. Es lo que dice el reglamento, y el programa
        # no lo disimula: el tablero sale atenuado.
        control = controlador_con(Color.NEGRO)
        assert control.color_que_juega() is None
        assert control.aplicar_jugada("e7e5") is False
        assert control.partida.historial == []

    def test_con_los_dos_colores_mueve_quien_tenga_el_turno(self):
        control = controlador_con(None)
        assert control.color_que_juega() is Color.BLANCO
        control.aplicar_jugada("e2e4")
        assert control.color_que_juega() is Color.NEGRO
        control.aplicar_jugada("e7e5")
        assert control.color_que_juega() is Color.BLANCO

    def test_con_los_dos_colores_se_juega_la_partida_entera(self):
        control = controlador_con(None)
        for jugada in ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"):
            assert control.aplicar_jugada(jugada) is True, jugada
        assert len(control.partida.historial) == 6

    def test_terminada_la_partida_no_mueve_nadie(self):
        control = controlador_con(None)
        # Mate de la dama: Legal, corta la partida.
        for jugada in ("e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"):
            control.aplicar_jugada(jugada)
        assert control.partida.esta_terminada()
        assert control.color_que_juega() is None


class TestPuedeMoverPieza:
    def test_solo_mueve_el_color_que_tiene_el_turno(self):
        control = controlador_con(None)
        blancas = control.partida.tablero.obtener(Posicion(4, 1))  # peón de e2
        negras = control.partida.tablero.obtener(Posicion(4, 6))  # peón de e7
        assert control.puede_mover_pieza(blancas) is True
        assert control.puede_mover_pieza(negras) is False

    def test_no_se_puede_mover_nada_sin_turno(self):
        # Elegir negras sin rival: hay piezas pero ninguna se puede mover.
        control = controlador_con(Color.NEGRO)
        blancas = control.partida.tablero.obtener(Posicion(4, 1))
        assert control.puede_mover_pieza(None) is False
        assert control.puede_mover_pieza(blancas) is False

    def test_no_es_la_ultima_pieza_que_anda(self):
        # La versión "de una pieza" tiene que seguir a la del color, no al revés.
        control = controlador_con(Color.BLANCO)
        assert control.puede_mover_pieza(control.partida.tablero.obtener(Posicion(4, 1))) is True
        control.aplicar_jugada("e2e4")
        assert control.puede_mover_pieza(control.partida.tablero.obtener(Posicion(4, 6))) is False
