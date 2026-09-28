"""Pruebas de la frontera entre la vista y el hilo que la ejecuta.

Lo que se comprueba aquí es una promesa, no un resultado: que **cualquier** vista
que cumpla el contrato sirve, y que el puente de hilos hace su trabajo sin
tocar la ventana.

Son tres cosas:

* El contrato. Se comprueba que ``PartidaView`` (consola) y ``VistaGUI``
  (ventana) tienen exactamente los mismos métodos públicos, aunque no se
  parezca nada entre ellas. Eso es lo que permite cambiar una por otra sin
  tocar el controlador.
* La conformidad. Se usa ``runtime_checkable`` para que el error salga al
  arrancar y no a mitad de una partida, tres horas después.
* El puente. Que el trabajo corra en otro hilo, que avise de cómo terminó y
  que no se pueda arrancar dos veces.

La vista de ventana no se instancia aquí: esto no necesita pantalla. Para
comprobar que de verdad dibuja y que un hilo real la maneja está
``smoke_vista_gui.py``, que sí abre ventanas y se ejecuta a mano.
"""

from __future__ import annotations

import threading

import pytest

from views.hilo import PuenteHilos
from views.interfaz import (
    OPCIONES_ARCHIVO,
    OPCIONES_INICIO,
    OPCIONES_PARTIDA,
    InterfazVista,
    texto_del_error,
)
from views.partida_view import PartidaView
from views.vista_gui import VistaGUI

# El contrato, escrito a mano y no sacado del Protocol a propósito. Si alguien
# añade un método al contrato, esta lista deja de cuadrar y hay que decidir a
# propósito qué vista lo implementa. Sin esto, añadir un método a ciegas
# rompería las dos vistas en tiempo de ejecución sin que se-enterase nadie.
CONTRATO = {
    # Pintar: no esperan, el controlador sigue avanzando.
    "escribir", "titulo", "mostrar_tablero", "mostrar_partidas", "mostrar_historial",
    "mostrar_fen", "mostrar_ayuda", "mostrar_mensaje", "mostrar_error",
    # Preguntar: sí esperan, y por eso son el punto que habría que cambiar para
    # tener una ventana con botones de verdad en lugar de con diálogos.
    "menu_inicio", "menu_partida", "menu_archivo", "elegir_color",
    "pedir_confirmacion", "pedir_jugada", "pedir_texto_opcional", "pedir_texto",
}


def _atributos_del_protocolo(protocolo: type) -> set[str]:
    """Los nombres que un ``Protocol`` declara, en cualquier versión de Python.

    ``Protocol.__protocol_attrs__`` es la forma oficial, pero **solo existe desde
    la 3.12**. En la 3.10 y la 3.11 no está, y el atributo se hadAccess da
    ``AttributeError``, que es exactamente lo que pasó en la CI al probar la
    3.10: el proyecto declara ``requires-python = ">=3.10"``, así que la prueba
    tiene que funcionar también ahí.

    El recurso es el atributo oficial cuando existe y, si no, la lista de
    miembros del propio ``Protocol``. Sale lo mismo en los dos casos **para este
    contrato**, porque aquí todos los miembros son métodos definidos con
    ``def`` y no hay miembros de datos ni propiedades declaradas sin
    implementar. Por eso el recurso está en la prueba y no en
    ``views/interfaz.py``: es una compatibilidad de la comprobación, no una
    diferencia en el contrato.

    Si algún día el ``Protocol`` declarara algo que no sea un método (un
    ``nombre: str`` sin valor, por ejemplo), este recurso dejaría de coincidir
    con ``__protocol_attrs__`` en la 3.10 y la prueba lo diría en la 3.12, que es
    justo cuando hay que darse cuenta.
    """
    declarados = getattr(protocolo, "__protocol_attrs__", None)
    if declarados is not None:
        return set(declarados)
    return {
        nombre
        for nombre, valor in vars(protocolo).items()
        if not nombre.startswith("_") and (callable(valor) or isinstance(valor, property))
    }


# ----------------------------------------------------------------------
# El contrato
# ----------------------------------------------------------------------

class TestElContrato:
    def test_el_contracto_no_se_va_a_ampliar_solas(self) -> None:
        declarados = _atributos_del_protocolo(InterfazVista)
        assert declarados == CONTRATO

    @pytest.mark.parametrize("vista", [PartidaView, VistaGUI])
    def test_cualquier_vista_tiene_el_contrato_completo(self, vista: type) -> None:
        # Se mira la clase, no un ejemplar: instanciar ``VistaGUI`` pide una
        # ventana y estas pruebas no deben necesitar pantalla.
        faltan = {m for m in CONTRATO if not callable(getattr(vista, m, None))}
        assert faltan == set()

    def test_la_consola_cumple_el_contrato(self) -> None:
        assert isinstance(PartidaView(), InterfazVista)

    def test_una_vista_incompleta_se_detecta(self) -> None:
        # El caso negativo: por qué sirve ``runtime_checkable``. Una clase con
        # un método de menos no es una vista, y hay que enterarse al principio.
        class VistaIncompleta:
            def escribir(self, texto: str = "") -> None:
                pass

        assert not isinstance(VistaIncompleta(), InterfazVista)

    def test_una_vista_que_no_hereda_nada_tambien_sirve(self) -> None:
        # Lo que da igual es cumplir el contrato, no heredar de la vista de
        # consola. Esta clase se construye con ``type`` y no tiene nada que ver
        # con ``PartidaView``, y aun así el controlador la aceptaría sin
        # enterarse.
        #
        # Los métodos se crean de verdad en el cuerpo de la clase (y no con un
        # ``__getattr__``) porque ``runtime_checkable`` mira la clase con
        # ``getattr_static``, que se salta el ``__getattr__`` a propósito: para
        # el chequeo solo existen los atributos de verdad.
        VistaAjena = type(
            "VistaAjena",
            (),
            {metodo: (lambda self, *a, **k: None) for metodo in CONTRATO},
        )
        assert isinstance(VistaAjena(), InterfazVista)

    def test_las_opciones_de_menu_una_sola_vez(self) -> None:
        # Las tres vistas leen las opciones de ``views.interfaz`` y no de la
        # consola. Es lo que evita que los menús se separen al añadir uno nuevo.
        assert PartidaView.OPCIONES_INICIO == OPCIONES_INICIO
        assert PartidaView.OPCIONES_PARTIDA == OPCIONES_PARTIDA
        assert PartidaView.OPCIONES_ARCHIVO == OPCIONES_ARCHIVO
        assert VistaGUI.OPCIONES_INICIO == OPCIONES_INICIO
        assert VistaGUI.OPCIONES_PARTIDA == OPCIONES_PARTIDA
        assert VistaGUI.OPCIONES_ARCHIVO == OPCIONES_ARCHIVO


class TestErroresCompartidos:
    """Los tres casos de ``texto_del_error``, que las dos vistas comparten.

    Se prueban los tres porque se distinguen por algo que se ve: un error
    redactado para la persona, un mensaje del controlador y un fallo
    inesperado. Si las dos vistas los trataran de forma distinta, sería un bug
    difícil de ver, y por eso la función vive fuera de ellas.
    """

    def test_un_error_de_ajedrez_se_atreve_a_explicar(self) -> None:
        from models.errores import ErrorAjedrez

        assert texto_del_error(ErrorAjedrez("la casilla estaba vacía")).startswith(
            "No se pudo completar la acción:"
        )

    def test_un_mensaje_del_controlador_no_se_disfraza_de_error(self) -> None:
        # Un fallo de disco lo ha redactado el controlador para que se lea bien;
        # si se le añadiera "error inesperado" haría pensar en un fallo del
        # programa cuando no lo es.
        assert texto_del_error("no se pudo escribir en disco") == "no se pudo escribir en disco"

    def test_una_excepcion_inesperada_dice_cual_es(self) -> None:
        # Aquí sí interesa el tipo: es lo único que dice qué está fallando.
        assert texto_del_error(ValueError("raro")) == "Error inesperado (ValueError): raro"


# ----------------------------------------------------------------------
# El puente de hilos
# ----------------------------------------------------------------------

class TestPuenteHilos:
    def test_el_trabajo_no_corre_en_el_hilo_principal(self) -> None:
        visto: list[str] = []
        puente = PuenteHilos(lambda: visto.append(threading.current_thread().name))
        puente.arrancar()
        puente.esperar(5)
        assert visto and visto[0] != threading.main_thread().name
        assert puente.en_hilo_principal() is True

    def test_avisa_al_terminar_con_el_resultado(self) -> None:
        recibidos: list[object] = []
        puente = PuenteHilos(lambda: 42, al_terminar=recibidos.append)
        puente.arrancar()
        puente.esperar(5)
        assert recibidos == [42]

    def test_sin_terminar_todavia_sigue_vivo(self) -> None:
        esperando = threading.Event()
        puente = PuenteHilos(esperando.wait)
        assert puente.vivo is False  # aún ni arrancado
        puente.arrancar()
        esperando.set()
        puente.esperar(5)
        assert puente.vivo is False  # ya terminó

    def test_un_error_llega_a_al_fallar_y_no_se_traga(self) -> None:
        # Un hilo que muere con una excepción deja el programa con la ventana
        # puesta y la partida a medias. El puente lo recoge y lo avisa, y el
        # original se conserva entero para poder enseñarlo.
        vistos: list[BaseException] = []
        puente = PuenteHilos(lambda: 1 / 0, al_fallar=vistos.append)
        puente.arrancar()
        puente.esperar(5)
        assert len(vistos) == 1
        assert isinstance(vistos[0], ZeroDivisionError)

    def test_arrancar_dos_veces_no_se_puede(self) -> None:
        # Da igual que el trabajo tarde o no: lo que se impide es perder la
        # referencia al primer hilo, que dejaría dos partidas a la vez.
        esperando = threading.Event()
        puente = PuenteHilos(esperando.wait)
        puente.arrancar()
        with pytest.raises(RuntimeError):
            puente.arrancar()
        esperando.set()
        puente.esperar(5)

    def test_los_mensajes_de_error_no_se_pierden(self) -> None:
        # Un error raro (aquí, salir a la calle) también se recoge: el puente
        # no distingue entre unas y otras.
        vistos: list[BaseException] = []
        puente = PuenteHilos(lambda: sys_exit(), al_fallar=vistos.append)
        puente.arrancar()
        puente.esperar(5)
        assert len(vistos) == 1


def sys_exit():
    raise KeyboardInterrupt("interrumpido a propósito")
