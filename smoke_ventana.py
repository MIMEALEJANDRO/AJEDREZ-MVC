"""Prueba de humo de la ventana jugable: ``python smoke_ventana.py``.

Comprueba lo que las pruebas de ``tests/`` no pueden comprobar, porque allí no
se abre ninguna ventana: que **lo que se ve y lo que se clican son la misma
casilla**.

Es la prueba que hizo falta cuando el tablero salía del revés. El síntoma era
que las piezas negras aparecían abajo y, al hacer clic en una de ellas, se movía
una blanca. Ni el modelo ni el controlador tienen nada que ver: el error estaba
en que el dibujo colocaba cada casilla en una fila de pantalla y el clic la
buscaba en la contraria. Por eso la comprobación es *visual*: se leen del
lienzo los números de fila y las letras de columna que se han dibujado de
verdad, y se deduce de ahí dónde ha quedado cada casilla, en vez de fiarse de la
función que hace el mapeo (que es justo lo que hay que demostrar).

Lo que se comprueba:

* los números y las letras dibujados dicen qué casilla hay en cada sitio,
* la pieza pintada en el centro de una casilla es la del modelo,
* un clic en el sitio donde se ve una pieza selecciona esa misma pieza,
* al girar el tablero sigue cumpliéndose (y ahora con el 180º correcto),
* con "los dos colores" el tablero no se atenúa nunca, porque siempre es tu turno,
* al elegir el color, el tablero se coloca solo con ese color abajo.

No forma parte de la batería de pruebas: necesita pantalla y abre ventanas. Se
ejecuta a mano con ``python smoke_ventana.py``.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from models.enums import Color  # noqa: E402
from models.pieza import SIMBOLOS  # noqa: E402
from models.posicion import Posicion  # noqa: E402
from views.ventana import (  # noqa: E402
    FONDO,
    LADO_CASILLA,
    MARGEN,
    VentanaAjedrez,
)

fallos: list[str] = []


def comprobar(condicion: bool, descripcion: str) -> None:
    print(f"  {'OK   ' if condicion else 'FALLO'} {descripcion}")
    if not condicion:
        fallos.append(descripcion)


# ---------------------------------------------------------------------------
# Lectura del lienzo: qué se ve, según lo que se ha dibujado de verdad
# ---------------------------------------------------------------------------

SIMBOLOS_TODOS = set(SIMBOLOS.values())


def textos(ventana: VentanaAjedrez) -> list[tuple[float, float, str]]:
    """Los textos del lienzo como ``(x, y, texto)``, en orden de dibujo."""
    return [
        (
            float(ventana.lienzo.coords(item)[0]),
            float(ventana.lienzo.coords(item)[1]),
            str(ventana.lienzo.itemcget(item, "text")),
        )
        for item in ventana.lienzo.find_all()
        if ventana.lienzo.type(item) == "text"
    ]


def fila_de_pantalla(y: float) -> int:
    """Fila de pantalla (0 = arriba) en la que está algo a esa altura."""
    return int((y - MARGEN) // LADO_CASILLA)


def columna_de_pantalla(x: float) -> int:
    """Columna de pantalla (0 = izquierda) en la que está algo a ese ancho."""
    return int((x - MARGEN) // LADO_CASILLA)


def casilla_bajo(ventana: VentanaAjedrez, x: float, y: float) -> tuple[int, int]:
    """La casilla de *pantalla* (columna, fila) que hay bajo un punto."""
    return columna_de_pantalla(x), fila_de_pantalla(y)


def rotulo_de_fila(ventana: VentanaAjedrez, fila_pantalla: int) -> str | None:
    """El número de fila que se ha dibujado a la altura de esa fila."""
    for _, y, texto in textos(ventana):
        if texto in "12345678" and len(texto) == 1 and fila_de_pantalla(y) == fila_pantalla:
            return texto
    return None


def rotulos_de_columna(ventana: VentanaAjedrez) -> dict[int, str]:
    """Las letras de columna dibujadas, por columna de pantalla.

    Se leen **todas** las que hay fuera del tablero (las que se dibujan en el
    borde de arriba y en el de abajo). Las de arriba y las de abajo tienen que
    decir lo mismo: si no, el tablero está mal colocado en horizontal.
    """
    encontradas: dict[int, str] = {}
    for x, _, texto in textos(ventana):
        if len(texto) == 1 and texto in "abcdefgh":
            encontradas.setdefault(columna_de_pantalla(x), texto)
    return encontradas


def simbolo_en(ventana: VentanaAjedrez, x: float, y: float) -> str | None:
    """El símbolo de pieza pintado en el centro de una casilla, si hay alguno."""
    for px, py, texto in textos(ventana):
        if texto in SIMBOLOS_TODOS and abs(px - x) < LADO_CASILLA / 2 and abs(py - y) < LADO_CASILLA / 2:
            return texto
    return None


def atenuado(ventana: VentanaAjedrez) -> int:
    """Cuántas casillas están cubiertas por la capa de "no es tu turno".

    Se cuentan solo los rectángulos de ese color: el tablero también usa
    cuadrados con trama para marcar la última jugada y el jaque, y esos no
    cuentan.
    """
    return sum(
        1
        for item in ventana.lienzo.find_all()
        if ventana.lienzo.type(item) == "rectangle"
        and ventana.lienzo.itemcget(item, "fill") == FONDO
        and ventana.lienzo.itemcget(item, "stipple")
    )


def clic_en(ventana: VentanaAjedrez, x: float, y: float) -> None:
    """Simula un clic del ratón en un punto del lienzo."""
    ventana.lienzo.event_generate("<Button-1>", x=int(x), y=int(y))
    ventana.root.update()


def clic_en_casilla_de_pantalla(ventana: VentanaAjedrez, columna: int, fila: int) -> None:
    """Clica en el centro de la casilla que está en ese sitio de la pantalla."""
    x = MARGEN + columna * LADO_CASILLA + LADO_CASILLA / 2
    y = MARGEN + fila * LADO_CASILLA + LADO_CASILLA / 2
    clic_en(ventana, x, y)


def elegir(ventana: VentanaAjedrez, valor: str) -> None:
    """Marca una opción del panel y hace lo mismo que si se pulsara."""
    ventana.opciones_color.set(valor)
    ventana._al_cambiar_color()


def silenciar_dialogos() -> None:
    """Contesta sola a los diálogos, para que la prueba no se quede esperando.

    Hace falta desde que cambiar de bando con la partida empezada pregunta si se
    reinicia: en una prueba de humo no hay nadie que conteste, y un
    ``askyesno`` sin responder deja el script colgado. Se sustituyen solo las dos
    funciones que se usan (``askyesno`` y ``askstring``), no la clase entera.

    Se contestan con "sí" y con un nombre fijo, que es lo que hace falta para que
    las comprobaciones sean estables.
    """
    import views.ventana as modulo

    modulo.messagebox.askyesno = lambda *argumentos, **opciones: True
    modulo.messagebox.askstring = lambda *argumentos, **opciones: "partida de prueba"


# ---------------------------------------------------------------------------
# Las comprobaciones
# ---------------------------------------------------------------------------


def parte_posicion_inicial(ventana: VentanaAjedrez) -> None:
    print("\n1) Posición inicial, sin girar")
    ventana.controlador.partida.reiniciar()
    ventana._nueva_partida()
    ventana._refrescar()

    comprobar(
        rotulo_de_fila(ventana, 0) == "8",
        "arriba del todo está la fila 8",
    )
    comprobar(rotulo_de_fila(ventana, 7) == "1", "abajo del todo está la fila 1")
    comprobar(
        [rotulo_de_fila(ventana, fila) for fila in range(8)] == list("87654321"),
        "las filas de arriba abajo son 8,7,6,5,4,3,2,1",
    )
    comprobar(
        [rotulos_de_columna(ventana).get(columna) for columna in range(8)] == list("abcdefgh"),
        "las columnas de izquierda a derecha son a,b,c,d,e,f,g,h",
    )

    # La casilla de abajo a la izquierda tiene que ser a1, con la torre blanca.
    simbolo = simbolo_en(
        ventana, MARGEN + LADO_CASILLA / 2, MARGEN + 7 * LADO_CASILLA + LADO_CASILLA / 2
    )
    comprobar(simbolo == "♖", f"abajo a la izquierda se ve la torre blanca (se ve {simbolo!r})")
    # Y la de arriba a la izquierda, a8, con la torre negra.
    simbolo = simbolo_en(ventana, MARGEN + LADO_CASILLA / 2, MARGEN + LADO_CASILLA / 2)
    comprobar(simbolo == "♜", f"arriba a la izquierda se ve la torre negra (se ve {simbolo!r})")

    # Un clic donde se ve el peón de e2 tiene que seleccionar el peón de e2.
    e2 = (4, 6)  # columna 4 (la "e"), fila de pantalla 6 (segunda desde abajo)
    clic_en_casilla_de_pantalla(ventana, *e2)
    comprobar(
        ventana.origen == Posicion(4, 1),
        f"el clic donde se ve e2 selecciona e2 (seleccionó {ventana.origen})",
    )
    destinos = sorted(movimiento.destino.notacion for movimiento in ventana.destinos)
    comprobar(destinos == ["e3", "e4"], f"se ofrecen los destinos de e2 (ofrece {destinos})")

    # Y un clic en e4 hace la jugada de verdad.
    clic_en_casilla_de_pantalla(ventana, 4, 4)
    historial = [movimiento.notacion for movimiento in ventana.controlador.partida.historial]
    comprobar(historial == ["e2-e4"], f"el clic en e4 juega e2-e4 (jugadas: {historial})")
    comprobar(ventana.origen is None, "la selección se limpia después de jugar")

    # Con un solo color, al pasar el turno el tablero se atenúa.
    comprobar(atenuado(ventana) == 64, f"el tablero se atenúa al pasar el turno ({atenuado(ventana)})")


def parte_los_dos_colores(ventana: VentanaAjedrez) -> None:
    print("\n2) Los dos colores")
    # Esta parte **empieza su propia partida**. Antes continuaba la de la parte 1,
    # y ya no puede: cambiar de bando con la partida empezada reinicia (para que
    # el bando y el turno no se queden descuadrados), así que al pasar a "ambas"
    # la partida se queda en blanco.
    #
    # "Los dos colores" es además el único modo en el que se juega una partida
    # entera: con un bando elegido el controlador no deja mover el color
    # contrario, así que tras tu jugada el turno se te escapa.
    elegir(ventana, "ambas")
    ventana._nueva_partida()
    comprobar(ventana.color is None, "el color jugador queda en ninguno")
    comprobar(
        ventana.controlador.color_jugador is None, "el controlador también juega con los dos"
    )
    comprobar(
        ventana.controlador.partida.turno is Color.BLANCO,
        "sin bando no hay a quién dar la primera jugada: empiezan las blancas",
    )
    comprobar(atenuado(ventana) == 0, f"el tablero NO se atenúa nunca ({atenuado(ventana)})")

    # Con los dos colores se puede mover el bando que tenga el turno...
    clic_en_casilla_de_pantalla(ventana, 4, 6)  # e2
    comprobar(ventana.origen == Posicion(4, 1), f"se elige el peón de e2 ({ventana.origen})")
    clic_en_casilla_de_pantalla(ventana, 4, 4)  # e4
    comprobar(
        [m.notacion for m in ventana.controlador.partida.historial] == ["e2-e4"],
        "y se juega e2-e4",
    )
    clic_en_casilla_de_pantalla(ventana, 4, 1)  # e7
    comprobar(
        ventana.origen == Posicion(4, 6), f"se elige el peón de e7 ({ventana.origen})"
    )
    clic_en_casilla_de_pantalla(ventana, 4, 3)  # e5
    comprobar(
        [m.notacion for m in ventana.controlador.partida.historial] == ["e2-e4", "e7-e5"],
        "y se juega e7-e5",
    )
    comprobar(atenuado(ventana) == 0, "y el tablero sigue sin atenuarse")

    # ...y el contrario, sin cambiar nada.
    clic_en_casilla_de_pantalla(ventana, 1, 6)  # b2
    comprobar(ventana.origen == Posicion(1, 1), "y ahora se elige un peón blanco (b2)")
    clic_en_casilla_de_pantalla(ventana, 1, 4)  # b4
    comprobar(
        [m.notacion for m in ventana.controlador.partida.historial]
        == ["e2-e4", "e7-e5", "b2-b4"],
        "y se juega b2-b4",
    )
    # Y a la vez se ve cuál fue la última jugada, que es lo único que el panel
    # enseña sin que se pulse nada.
    comprobar(
        ventana.etiqueta_ultima.cget("text") == "Blancas b2-b4",
        f"y el panel dice cuál fue la última jugada ({ventana.etiqueta_ultima.cget('text')!r})",
    )


def parte_elegir_color(ventana: VentanaAjedrez) -> None:
    print("\n3) Elegir color coloca el tablero y pone el turno de acuerdo")
    # Se empieza una partida nueva antes de elegir bando: así no hay jugadas que
    # perder y no salta el diálogo de confirmación.
    ventana._nueva_partida()
    elegir(ventana, "negras")
    comprobar(ventana.girada is True, "al elegir negras el tablero se gira")
    comprobar(
        rotulo_de_fila(ventana, 0) == "1", "girado, arriba del todo está la fila 1"
    )
    comprobar(rotulo_de_fila(ventana, 7) == "8", "girado, abajo del todo está la fila 8")
    comprobar(
        [rotulos_de_columna(ventana).get(columna) for columna in range(8)] == list("hgfedcba"),
        "girado, las columnas de izquierda a derecha son h,g,f,e,d,c,b,a",
    )
    simbolo = simbolo_en(
        ventana, MARGEN + LADO_CASILLA / 2, MARGEN + 7 * LADO_CASILLA + LADO_CASILLA / 2
    )
    comprobar(simbolo == "♜", f"abajo a la izquierda se ve la torre negra (se ve {simbolo!r})")

    # Lo que cambió con el arreglo: con negras **empiezan las negras**. Antes se
    # giraba la vista pero el turno se quedaba en las blancas y la partida
    # quedaba bloqueada (ninguna jugada era legal).
    comprobar(
        ventana.controlador.color_jugador is Color.NEGRO, "el bando del jugador es negro"
    )
    comprobar(
        ventana.controlador.partida.turno is Color.NEGRO,
        "y con negras empieza el turno de las negras",
    )
    comprobar(atenuado(ventana) == 0, f"el tablero se ilumina: es el turno de negras ({atenuado(ventana)})")

    # Se puede mover negro de entrada, sin tener que esperar a que mueva nadie.
    # En el tablero girado las columnas van del revés: la "e" es la cuarta desde
    # la derecha (columna 3) y la fila 7 es la segunda desde abajo (fila 6).
    clic_en_casilla_de_pantalla(ventana, 3, 6)  # e7
    comprobar(
        ventana.origen == Posicion(4, 6),
        f"el peón de e7 se puede pulsar de entrada (seleccionó {ventana.origen})",
    )
    clic_en_casilla_de_pantalla(ventana, 3, 4)  # e5
    comprobar(
        [m.notacion for m in ventana.controlador.partida.historial] == ["e7-e5"],
        "y se juega e7-e5 con el mismo clic",
    )
    comprobar(
        ventana.etiqueta_ultima.cget("text") == "Negras e7-e5",
        f"el panel dice 'Negras e7-e5' ({ventana.etiqueta_ultima.cget('text')!r})",
    )

    # Y ahora sí es el turno de las blancas: el tablero se atenúa y el peón de e7
    # ya no se puede tocar, porque no es el turno del bando elegido.
    comprobar(
        atenuado(ventana) == 64,
        f"tras la jugada de negras se atenúa: es el turno de las blancas ({atenuado(ventana)})",
    )
    clic_en_casilla_de_pantalla(ventana, 3, 6)  # e7
    comprobar(ventana.origen is None, "no se puede mover negro cuando es el turno de blanco")


def parte_panel_fen(ventana: VentanaAjedrez) -> None:
    print("\n5) El detalle de FEN e historial")
    # Se vuelve a blancas para tener una partida normal y sin jugadas.
    ventana._nueva_partida()
    elegir(ventana, "blancas")
    ventana._nueva_partida()

    # De salida no se ve ni el FEN ni el historial, y el botón ofrece enseñarlos.
    comprobar(not ventana._panel_fen_visible, "el panel de FEN nace oculto")
    comprobar(
        ventana.boton_fen.cget("text") == "Mostrar FEN",
        f"el botón pone 'Mostrar FEN' ({ventana.boton_fen.cget('text')!r})",
    )
    comprobar(ventana.panel_fen.grid_info() == {}, "y no está colocado en pantalla")

    # Al pulsarlo aparece, con su botón de copiar, y el botón cambia de texto.
    ventana.boton_fen.invoke()
    comprobar(ventana._panel_fen_visible, "al pulsarlo el panel se muestra")
    comprobar(
        ventana.boton_fen.cget("text") == "Ocultar FEN",
        f"y el botón pasa a 'Ocultar FEN' ({ventana.boton_fen.cget('text')!r})",
    )
    comprobar(ventana.campo_fen.get() == ventana.controlador.partida.a_fen(), "el FEN es el de ahora")

    # Se actualiza en cada jugada mientras esté abierto.
    clic_en_casilla_de_pantalla(ventana, 4, 6)  # e2
    clic_en_casilla_de_pantalla(ventana, 4, 4)  # e4
    comprobar(
        ventana.campo_fen.get() == ventana.controlador.partida.a_fen(),
        "el FEN se actualiza al jugar, con el panel abierto",
    )
    comprobar(
        "e2-e4" in ventana.historial.get("1.0", "end"),
        "y el historial también",
    )

    # Y al pulsarlo otra vez se esconde.
    ventana.boton_fen.invoke()
    comprobar(not ventana._panel_fen_visible, "al pulsarlo otra vez se oculta")
    comprobar(ventana.boton_fen.cget("text") == "Mostrar FEN", "y el botón vuelve a su texto")

    # Empieza oculta en cada partida nueva.
    ventana.boton_fen.invoke()
    ventana._nueva_partida()
    comprobar(
        not ventana._panel_fen_visible, "una partida nueva lo deja oculto otra vez"
    )


def parte_girar(ventana: VentanaAjedrez) -> None:
    print("\n4) Girar el tablero a mano")
    # Elegir blancas deja el tablero en su posición normal (lo hizo la parte 3
    # con negras), así que aquí se empieza de Orientation(blanco abajo).
    elegir(ventana, "blancas")
    comprobar(ventana.girada is False, "con blancas el tablero queda derecho")
    comprobar(rotulo_de_fila(ventana, 0) == "8", "arriba del todo la fila 8")
    comprobar(
        [rotulos_de_columna(ventana).get(columna) for columna in range(8)] == list("abcdefgh"),
        "y las columnas de izquierda a derecha son a..h",
    )
    ventana._nueva_partida()
    clic_en_casilla_de_pantalla(ventana, 4, 6)  # e2
    comprobar(ventana.origen == Posicion(4, 1), "el clic en e2 sigue seleccionando e2")
    clic_en_casilla_de_pantalla(ventana, 4, 4)  # e4
    comprobar(
        [m.notacion for m in ventana.controlador.partida.historial] == ["e2-e4"],
        "y el clic en e4 sigue jugando e2-e4",
    )

    # Y girada, el 180º también tiene que ser coherente en las dos direcciones:
    # lo que se ve arriba a la derecha es la casilla a1.
    ventana._girar()
    comprobar(rotulo_de_fila(ventana, 0) == "1", "girada a mano: arriba del todo la fila 1")
    comprobar(
        [rotulos_de_columna(ventana).get(columna) for columna in range(8)] == list("hgfedcba"),
        "girada a mano: las columnas son h..a",
    )
    ventana._nueva_partida()
    clic_en_casilla_de_pantalla(ventana, 3, 1)  # e2, arriba del todo
    comprobar(ventana.origen == Posicion(4, 1), "girada, el clic donde se ve e2 selecciona e2")
    clic_en_casilla_de_pantalla(ventana, 3, 3)  # e4
    comprobar(
        [m.notacion for m in ventana.controlador.partida.historial] == ["e2-e4"],
        "y el clic donde se ve e4 juega e2-e4",
    )
    # Y con el tablero girado la columna también va del revés: la "e" es la
    # cuarta desde la derecha.
    clic_en_casilla_de_pantalla(ventana, 3, 6)  # e7, abajo del todo
    comprobar(
        ventana.origen is None, "el peón de e7 (abajo del todo) no se puede pulsar (es de negras)"
    )


def main() -> int:
    root = tk.Tk()
    # La ventana tiene que estar mapeada: Tk no reparte los eventos generados
    # con ``event_generate`` a una ventana retirada, así que con ``withdraw()``
    # ningún clic llegaría al tablero y la prueba no comprobaría nada. Se deja
    # fuera de la pantalla y sin opacidad para no molestar.
    root.attributes("-alpha", 0.0)
    root.geometry("+%d+%d" % (20000, 20000))
    root.update()
    try:
        ventana = VentanaAjedrez(root)
        # Tras construir la ventana hay que dejarla asentar: el primer
        # ``event_generate`` se pierde si Tk todavía no ha procesado el mapa de la
        # ventana, y la comprobación fallaría sin que nada esté roto.
        for _ in range(3):
            root.update()
        silenciar_dialogos()
        parte_posicion_inicial(ventana)
        parte_los_dos_colores(ventana)
        parte_elegir_color(ventana)
        parte_girar(ventana)
        parte_panel_fen(ventana)
    finally:
        root.destroy()

    print()
    if fallos:
        print(f"{len(fallos)} comprobaciones fallaron:")
        for una in fallos:
            print(f"  - {una}")
        return 1
    print("Todo correcto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
