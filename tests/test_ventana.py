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
from views.interfaz import InterfazVista  # noqa: E402
from views.ventana import SalidaDeConsola, VentanaAjedrez  # noqa: E402


def _atributos_del_protocolo(protocolo: type) -> set[str]:
    """Los nombres que un ``Protocol`` declara, en cualquier versión de Python.

    ``Protocol.__protocol_attrs__`` es la forma oficial, pero **solo existe desde
    la 3.12**. En la 3.10 y la 3.11 el acceso da ``AttributeError``, que es
    exactamente lo que pasó en la CI al probar la 3.10 con este archivo.

    El recurso es el atributo oficial cuando existe y, si no, la lista de
    miembros del propio ``Protocol``. Sale lo mismo en los dos casos **para este
    contrato**, porque sus seis miembros son métodos definidos con ``def`` y no
    hay miembros de datos. Por eso el recurso va aquí y no en
    ``views/interfaz.py``: es una compatibilidad de la comprobación, no una
    diferencia en el contrato.
    """
    declarados = getattr(protocolo, "__protocol_attrs__", None)
    if declarados is not None:
        return set(declarados)
    return {
        nombre
        for nombre, valor in vars(protocolo).items()
        if not nombre.startswith("_") and (callable(valor) or isinstance(valor, property))
    }


class TestElContrato:
    """El ``Protocol`` tiene que ser cierto, y esto es lo que lo vigila.

    El contrato declaraba 17 métodos (los de la consola y sus tres menús)
    cuando la única vista que existía implementaba seis. Un ``Protocol`` que su
    propia implementación incumple no es documentación, es una mentira; y como
    ``runtime_checkable`` solo comprueba que existan los métodos,
    ``isinstance`` devolvía ``False`` sin que nada lo delatara.

    Estos dos tests son la red que lo evita: si alguien añade un método al
    contrato y no lo implementa la pantalla, o al revés, fallan aquí.
    """

    def test_la_pantalla_cumple_el_contrato_completo(self, ventana):
        # El que de verdad importa: se instancia y se pregunta.
        assert isinstance(SalidaDeConsola(ventana), InterfazVista)

    def test_la_pantalla_no_declara_metodos_de_menus(self, ventana):
        # El otro lado del mismo acuerdo: el contrato no pide menús, porque no
        # hay ninguna pantalla que los tenga. Si alguien los vuelve a meter sin
        # una pantalla que los cumpla, esto salta.
        declarados = _atributos_del_protocolo(InterfazVista)
        assert declarados == {
            "escribir",
            "titulo",
            "mostrar_mensaje",
            "mostrar_error",
            "pedir_confirmacion",
            "elegir_color",
        }
        assert not [m for m in declarados if m.startswith(("menu_", "pedir_jugada", "mostrar_tablero"))]


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

    def test_con_negras_no_se_puede_mover_nada(self, ventana):
        # Elegir Negras sin rival: mueven las blancas y nadie las mueve, así que
        # no hay jugada posible. El tablero sale atenuado, y eso lo comprueba el
        # humo de la ventana; aquí se comprueba la regla.
        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()
        control = ventana.controlador
        assert control.color_jugador is Color.NEGRO
        assert control.partida.turno is Color.BLANCO
        assert control.color_que_juega() is None
        assert control.aplicar_jugada("e7e5") is False

    def test_con_blancas_se_juega_una_jugada_y_se_acaba_el_turno(self, ventana):
        # El caso bueno, y el que se ve al abrir el programa: con Blancas se juega
        # la primera jugada. Después el turno es del otro bando y la segunda no
        # entra. Es el límite del modo de un jugador.
        ventana.controlador.aplicar_jugada("e2e4")
        ventana._refrescar()
        assert ventana.controlador.partida.turno is Color.NEGRO
        assert ventana.controlador.color_que_juega() is None
        assert ventana.controlador.aplicar_jugada("e7e5") is False

    def test_partida_nueva_vuelve_a_dejarse_mover(self, ventana):
        # Tras una jugada (y solo esa), "Partida nueva" devuelve el turno.
        ventana.controlador.aplicar_jugada("e2e4")
        ventana._nueva_partida()
        control = ventana.controlador
        assert control.partida.historial == []
        assert control.partida.turno is Color.BLANCO
        assert control.aplicar_jugada("e2e4") is True

    def test_cambiar_de_bando_no_toca_la_partida(self, ventana):
        # El turno inicial ya no depende del bando (siempre las blancas), así que
        # cambiar de bando a mitad de partida no reinicia nada ni pregunta: solo
        # cambia a quién le toca el ratón. Antes sí reiniciaba, y por eso había un
        # diálogo de confirmación que ya no hace falta.
        ventana.opciones_color.set("ambas")
        ventana._al_cambiar_color()
        ventana.controlador.aplicar_jugada("e2e4")
        ventana.controlador.aplicar_jugada("e7e5")
        assert len(ventana.controlador.partida.historial) == 2

        ventana.opciones_color.set("negras")
        ventana._al_cambiar_color()
        control = ventana.controlador
        assert control.color_jugador is Color.NEGRO
        assert len(control.partida.historial) == 2
        assert control.partida.turno is Color.BLANCO


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

    def test_con_los_dos_colores_dice_el_color_de_quien_movio(self, ambos):
        # La etiqueta dice quién movió, que se deduce del turno. En "los dos
        # colores" se juega entera, así que se ven los dos bandos.
        ambos.controlador.aplicar_jugada("e2e4")
        ambos._refrescar()
        assert ambos.etiqueta_ultima.cget("text") == "Blancas e2-e4"
        ambos.controlador.aplicar_jugada("e7e5")
        ambos._refrescar()
        assert ambos.etiqueta_ultima.cget("text") == "Negras e7-e5"
