"""Pruebas de la ventana con pantalla: el bando, el giro y los paneles.

A diferencia de ``test_ventana_mapeo.py``, que es cálculo puro y corre en
cualquier sitio, aquí **se abre una ventana de verdad**. Por eso estas pruebas
necesitan un servidor gráfico:

* en Linux, sin pantalla:  ``xvfb-run -a python -m pytest tests/test_ventana.py``
* en Windows o macOS:     ``python -m pytest`` (hay escritorio)

Si ``tkinter`` no puede abrir una pantalla, las pruebas se saltan con un motivo
claro en vez de fallar: es preferible no comprobar nada a que la batería entera
se caiga en un equipo sin escritorio.

Lo que se comprueba aquí es lo que **no** se puede comprobar sin pantalla: que la
ventana llame al controlador, que el botón de "Mostrar FEN" abra y cierre su
panel, y que la última jugada se actualice al mover y al deshacer. Todo lo demás
de la ventana (dónde cae cada casilla) está en ``test_ventana_mapeo.py``, que no
necesita nada de esto.
"""

from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter", reason="esta plataforma no trae tkinter")

from models.enums import Color  # noqa: E402
from views.ventana import VentanaAjedrez  # noqa: E402


@pytest.fixture
def root():
    """Una ``Tk()`` real, o la prueba se salta si no hay pantalla.

    Se esconde con ``withdraw`` para no dejar ventanas abiertas mientras corren
    las pruebas, pero la ventana sí se construye entera: los widgets existen y se
    pueden preguntar por ellos (``winfo_ismapped``, ``cget("text")``...), que es
    justo lo que se quiere comprobar.
    """
    try:
        ventana = tk.Tk()
    except tk.TclError as error:  # pragma: no cover - depende del entorno
        pytest.skip(f"no hay pantalla disponible: {error}")
    ventana.withdraw()
    yield ventana
    try:
        ventana.destroy()
    except tk.TclError:  # pragma: no cover
        pass


@pytest.fixture
def ventana(root):
    return VentanaAjedrez(root)


@pytest.fixture
def ambos(ventana):
    """La ventana en modo "Los dos colores", que es el único que deja jugar la
    partida entera.

    Hace falta porque con un bando elegido el controlador no deja mover el color
    contrario, así que una jugada y su respuesta no se pueden hacer seguidas. Es
    el límite del modo "un solo color" sin rival, que está anotado en el README;
    aquí se elude poniendo el selector en "ambos", que es lo que hace quien
    quiere practicar de verdad.
    """
    ventana.opciones_color.set("ambas")
    ventana._al_cambiar_color()
    return ventana


# ---------------------------------------------------------------------------
# Bando y giro del tablero
# ---------------------------------------------------------------------------

class TestBandoYGiro:
    def test_por_defecto_se_juega_con_blancas_y_sin_girar(self, ventana):
        assert ventana.color is Color.BLANCO
        assert ventana.girada is False
        assert ventana.controlador.color_jugador is Color.BLANCO
        assert ventana.controlador.partida.turno is Color.BLANCO

    def test_elegir_negras_gira_el_tablero(self, ventana):
        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()
        assert ventana.color is Color.NEGRO
        assert ventana.girada is True

    def test_elegir_blancas_deja_el_tablero_sin_girar(self, ventana):
        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()
        ventana.opciones_color.set("blancas")
        ventana._al_cambiar_color()
        assert ventana.girada is False

    def test_los_dos_colores_no_giran_el_tablero(self, ventana):
        # Sin bando propio no hay lado "propio", así que el tablero se queda como
        # esté (puede haberlo girado a mano el botón).
        ventana.opciones_color.set("ambas")
        ventana._al_cambiar_color()
        assert ventana.color is None
        assert ventana.girada is False

    def test_con_negras_empiezan_las_negras(self, ventana):
        # El bug: se giraba la vista pero el turno se quedaba en las blancas y
        # la partida quedaba bloqueada.
        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()
        assert ventana.controlador.partida.turno is Color.NEGRO

    def test_con_negras_se_puede_hacer_la_primera_jugada(self, ventana):
        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()
        control = ventana.controlador
        assert control.aplicar_jugada("e7e5") is True
        assert len(control.partida.historial) == 1

    def test_partida_nueva_mantiene_el_bando_y_el_turno(self, ventana):
        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()
        ventana._nueva_partida()
        control = ventana.controlador
        assert control.color_jugador is Color.NEGRO
        assert control.partida.turno is Color.NEGRO
        assert control.partida.historial == []
        assert control.aplicar_jugada("e7e5") is True

    def test_cambiar_de_bando_con_partida_empezada_pregunta(self, ventana, monkeypatch):
        # Sin el aviso, cambiar el bando a mitad de partida perdería las jugadas
        # sin avisar. Se comprueba que se pregunta, y que si se dice que no se
        # vuelve al bando anterior (included el botón de radio).
        ventana.controlador.aplicar_jugada("e2e4")
        assert ventana.controlador.partida.historial

        preguntas: list[str] = []

        def no(*args, **kwargs):
            preguntas.append(args[1] if len(args) > 1 else kwargs.get("message", ""))
            return False

        monkeypatch.setattr("views.ventana.messagebox.askyesno", no)
        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()

        assert preguntas, "no se preguntó por el cambio de bando"
        assert ventana.color is Color.BLANCO
        assert ventana.opciones_color.get() == "blancas"
        assert len(ventana.controlador.partida.historial) == 1

    def test_cambiar_de_bando_aceptando_reinicia_la_partida(self, ventana, monkeypatch):
        ventana.controlador.aplicar_jugada("e2e4")
        monkeypatch.setattr("views.ventana.messagebox.askyesno", lambda *a, **k: True)
        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()
        control = ventana.controlador
        assert control.color_jugador is Color.NEGRO
        assert control.partida.turno is Color.NEGRO
        assert control.partida.historial == []
        assert control.clave_guardada is None


# ---------------------------------------------------------------------------
# El detalle de FEN e historial: oculto de salida
# ---------------------------------------------------------------------------

class TestPanelDeFen:
    """El boton "Mostrar FEN" y lo que hay detras.

    Lo que se comprueba aqui es la razon de existir del boton: sin pulsar nada no
    se ve el FEN ni el historial, y lo unico que se ve sobre la partida es la
    ultima jugada. Antes esas dos cosas estaban siempre a la vista, que es mucha
    informacion para alguien que solo quiere mover una pieza.
    """

    def test_el_panel_nace_oculto(self, ventana):
        assert ventana._panel_fen_visible is False
        assert ventana.boton_fen.cget("text") == "Mostrar FEN"
        # grid_info() dice si un widget esta colocado en la rejilla: vacio
        # significa que no lo esta, que es como se comprueba "oculto" en tkinter.
        assert ventana.panel_fen.grid_info() == {}

    def test_el_boton_muestra_el_panel(self, ventana):
        ventana.boton_fen.invoke()
        assert ventana._panel_fen_visible is True
        assert ventana.boton_fen.cget("text") == "Ocultar FEN"
        assert ventana.panel_fen.grid_info() != {}

    def test_el_boton_lo_vuelve_a_ocultar(self, ventana):
        ventana.boton_fen.invoke()
        ventana.boton_fen.invoke()
        assert ventana._panel_fen_visible is False
        assert ventana.boton_fen.cget("text") == "Mostrar FEN"
        assert ventana.panel_fen.grid_info() == {}

    def test_al_abrirlo_muestra_el_fen_de_esa_partida(self, ventana):
        ventana.controlador.aplicar_jugada("e2e4")
        ventana.boton_fen.invoke()
        assert ventana.campo_fen.get() == ventana.controlador.partida.a_fen()

    def test_se_actualiza_en_cada_jugada_mientras_esta_abierto(self, ventana):
        ventana.boton_fen.invoke()
        antes = ventana.campo_fen.get()
        ventana.controlador.aplicar_jugada("e2e4")
        ventana._refrescar()
        assert ventana.campo_fen.get() != antes
        assert ventana.campo_fen.get() == ventana.controlador.partida.a_fen()

    def test_empieza_oculto_tras_partida_nueva(self, ventana):
        ventana.boton_fen.invoke()
        assert ventana._panel_fen_visible is True
        ventana._nueva_partida()
        assert ventana._panel_fen_visible is False
        assert ventana.boton_fen.cget("text") == "Mostrar FEN"


class TestUltimaJugada:
    def test_al_empezar_dice_que_no_hay_jugadas(self, ventana):
        assert ventana.etiqueta_ultima.cget("text") == "Todavía no hay jugadas"

    def test_despues_de_mover_dice_el_color_y_la_casilla(self, ventana):
        ventana.controlador.aplicar_jugada("e2e4")
        ventana._refrescar()
        assert ventana.etiqueta_ultima.cget("text") == "Blancas e2-e4"

    def test_se_actualiza_en_cada_jugada(self, ambos):
        ambos.controlador.aplicar_jugada("e2e4")
        ambos._refrescar()
        ambos.controlador.aplicar_jugada("e7e5")
        ambos._refrescar()
        assert ambos.etiqueta_ultima.cget("text") == "Negras e7-e5"

    def test_tras_deshacer_vuelve_a_la_anterior(self, ambos):
        ambos.controlador.aplicar_jugada("e2e4")
        ambos.controlador.aplicar_jugada("e7e5")
        ambos._refrescar()
        ambos._deshacer()
        assert ambos.etiqueta_ultima.cget("text") == "Blancas e2-e4"

    def test_tras_deshacer_todas_vuelve_a_no_haber_jugadas(self, ventana):
        ventana.controlador.aplicar_jugada("e2e4")
        ventana._refrescar()
        ventana._deshacer()
        assert ventana.etiqueta_ultima.cget("text") == "Todavía no hay jugadas"
        assert ventana.controlador.partida.historial == []

    def test_con_negras_dice_negras(self, ventana):
        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()
        ventana.controlador.aplicar_jugada("e7e5")
        ventana._refrescar()
        assert ventana.etiqueta_ultima.cget("text") == "Negras e7-e5"
