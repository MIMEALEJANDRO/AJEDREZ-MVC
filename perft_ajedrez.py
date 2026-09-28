"""Perft: contar el árbol de jugadas, para comprobar las reglas de verdad.

    python perft_ajedrez.py                 # comprueba las 6 posicionesANDARD
    python perft_ajedrez.py --diferencial   # una a una contra python-chess
    python perft_ajedrez.py --fuzz 100      # 100 partidas al azar, nodo a nodo

Qué es el perft
---------------

``perft(n)`` es el número de rutas de ``n`` jugadas legales que hay desde una
posición. No dice si la jugada es buena: dice cuántas hay, y eso obliga a que
todo cuadre a la vez, porque cualquier error de una regla (un enroque que no se
debe permitir, un peón que no captura al paso, una promoción que se pierde) sale
inmediato como un número que no coincide.

Por eso es la comprobación más dura que se puede hacer de un generador de
jugadas: 197281 rutas de cuatro jugadas desde la posición inicial no se
inventan, y un fallo que solo se dé en una posición rarísima sigue saliendo si
las posiciones de la tabla están elegidas para eso (hay una de enroque, una de
en passant, una de promoción y una con jaque).

De dónde salen los números de la tabla
--------------------------------------

De ``python-chess``, no de memoria. La biblioteca es la referencia y la tabla se
generó con ella, que es también lo que hace el modo ``--diferencial``: comparar
contra los valores guardados detecta regresiones; comparar contra la biblioteca
descubre que la tabla misma estaba mal.

Lo que el perft ignora (y por qué)
----------------------------------

* **El historial y el estado de la partida.** Recorrer ``Partida.mover`` entero
  va a 50 nodos por segundo: en cada jugada rehace el análisis de la posición
  (genera las jugadas legales otra vez, escribe un FEN para la repetición y
  mira el material), y para el perft nada de eso cuenta. Aquí se camina por el
  tablero con ``Tablero.movimientos_legales`` y ``Tablero.aplicar``, que es la
  generación de jugadas y la geometría de verdad, y la única regla de partida
  que el tablero no conoce (perder los derechos de enroque) se pide a la clase
  que sí la sabe, ``Partida._registrar_derechos_enroque``. Lo que se mide
  sigue siendo el generador de jugadas del programa.
* **La casilla al paso no hay que mantenerla**: ``casilla_al_paso()`` se deduce
  de la última jugada, así que ``Tablero.aplicar`` ya la deja correcta.
* **La promoción se cuenta cuatro veces.** Un peón que llega a la última fila
  puede promociónar a dama, torre, alfil o caballo, y son cuatro jugadas
  distintas. ``Tablero.aplicar`` acepta las cuatro; el generador de jugadas no
  las separa (no puede: ``Movimiento`` solo guarda origen y destino, y la ventana
  pregunta la promoción al jugador después), así que el script las ramifica él.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from models.enums import Color, TipoPieza  # noqa: E402
from models.partida import Partida  # noqa: E402
from models.pieza import LETRAS_PROMOCION  # noqa: E402
from models.posicion import Movimiento, Posicion  # noqa: E402
from models.tablero import Tablero  # noqa: E402

# Orden de las cuatro piezas: por customary, dama, torre, alfil y caballo. El
# orden no altera los números, solo el recorrido del script.
PROMOCIONES = (TipoPieza.DAMA, TipoPieza.TORRE, TipoPieza.ALFIL, TipoPieza.CABALLO)

# Las seis posiciones de la tabla, con los valores de python-chess. Entre una y
# otra se va quitando algo que la anterior sí tenía: enroque por los dos lados,
# captura al paso, promoción con captura y sin ella, una posición donde el rey
# ya está en jaque.
POSICIONES = [
    ("Inicial", None, [20, 400, 8902, 197281]),
    (
        "Kiwipete",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        [48, 2039, 97862, 4085603],
    ),
    ("Al paso", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812, 43238]),
    (
        "Promoción",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        [6, 264, 9467, 422333],
    ),
    (
        "Enroque mixto",
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
        [44, 1486, 62379, 2103487],
    ),
    (
        "Jaque",
        "r4rk1/1pp1qppp/p1np1n2/1B2p1b1/4P3/1BN1P3/PPP2PPP/2KR3R w - - 0 1",
        [37, 1332, 46596, 1632807],
    ),
]


# ---------------------------------------------------------------------------
# El modelo
# ---------------------------------------------------------------------------

class _SoloTablero:
    """El mínimo que necesita ``Partida._registrar_derechos_enroque``.

    Ese método es la regla de partida que el tablero no puede tener (el tablero
    no sabe de reglas, solo de geometría) y solo usa ``self.tablero``. Se le
    presta un tablero y se llama al método de verdad, en vez de copiar el
    dictionaries de casillas iniciales aquí, que es donde se colaría un error si
    las dos cosas se desincronizasen.
    """

    def __init__(self, tablero: Tablero) -> None:
        self.tablero = tablero


def promociones_de(tablero: Tablero, movimiento: Movimiento) -> tuple[TipoPieza | None, ...]:
    """Las cuatro piezas con las que se puede seguir esta jugada.

    Solo hay pregunta cuando un peón llega a la última fila. En cualquier otro
    caso hay una sola forma de continuar la jugada y se devuelve un único valor.
    """
    pieza = tablero.obtener(movimiento.origen)
    if pieza is not None and pieza.tipo is TipoPieza.PEON and movimiento.destino.fila in (0, 7):
        return PROMOCIONES
    return (None,)


def jugadas(tablero: Tablero, color: Color) -> list[tuple[Movimiento, TipoPieza | None]]:
    """Las jugadas legales del color, con la promoción que corresponde a cada una."""
    return [
        (movimiento, promocion)
        for movimiento in tablero.movimientos_legales(color)
        for promocion in promociones_de(tablero, movimiento)
    ]


def perft(tablero: Tablero, color: Color, profundidad: int) -> int:
    """Rutas de ``profundidad`` jugadas desde la posición de ``tablero``."""
    if profundidad == 0:
        return 1
    reglas = _SoloTablero(tablero)
    total = 0
    for movimiento, promocion in jugadas(tablero, color):
        siguiente = tablero.clonar()
        pieza = siguiente.obtener(movimiento.origen)
        capturada = siguiente.aplicar(movimiento, promocion)
        reglas.tablero = siguiente
        Partida._registrar_derechos_enroque(reglas, movimiento, pieza, capturada)
        total += perft(siguiente, color.contrario, profundidad - 1)
    return total


def reparto(tablero: Tablero, color: Color, profundidad: int) -> dict[str, int]:
    """``perft`` nodo a nodo: cuántas rutas sale por cada primera jugada.

    Es lo que sirve para localizar un fallo: si el total no cuadra, el nodo que
    no cuadra es el que señala el error.
    """
    if profundidad == 0:
        return {}
    reglas = _SoloTablero(tablero)
    cuenta: dict[str, int] = {}
    for movimiento, promocion in jugadas(tablero, color):
        siguiente = tablero.clonar()
        pieza = siguiente.obtener(movimiento.origen)
        capturada = siguiente.aplicar(movimiento, promocion)
        reglas.tablero = siguiente
        Partida._registrar_derechos_enroque(reglas, movimiento, pieza, capturada)
        cuenta[notacion(movimiento, promocion)] = perft(siguiente, color.contrario, profundidad - 1)
    return cuenta


def notacion(movimiento: Movimiento, promocion: TipoPieza | None) -> str:
    """La jugada en notación de tablero: ``e7e8q``, ``e2e4``..."""
    texto = f"{movimiento.origen.notacion}{movimiento.destino.notacion}"
    if promocion is not None:
        texto += LETRA_DE[promocion]
    return texto


LETRA_DE = {tipo: letra for letra, tipo in LETRAS_PROMOCION.items()}


def promocion_de(movimiento: object) -> TipoPieza | None:
    """La pieza con la que python-chess quiere coronar, o ``None``.

    Ojo con el detalle, que es la razón de que esta función exista:
    ``Move.promotion`` de python-chess **no** es la letra del FEN, es el tipo de
    pieza como número (``chess.ROOK`` es el 4, ``chess.KNIGHT`` el 2...). Si se
    busca directamente en un diccionario de letras, no se encuentra nada, se
    devuelve ``None`` y el modelo corona a dama siempre. El síntoma era un
    "fuzz" que reportaba diferencias en cualquier partida que llegara a una
    coronación menor, cuando el motor las hace bien.

    ``piece_symbol`` es la operación inversa: convierte ese número en la letra
    ("r"), que es lo que sí entiende ``LETRAS_PROMOCION``.
    """
    import chess  # noqa: PLC0415

    if movimiento.promotion is None:
        return None
    return LETRAS_PROMOCION.get(chess.piece_symbol(movimiento.promotion))


# ---------------------------------------------------------------------------
# python-chess, la referencia
# ---------------------------------------------------------------------------

def requiere_chess() -> object:
    try:
        import chess  # noqa: PLC0415
    except ImportError:  # pragma: no cover - depende del entorno
        print(
            "Para el modo diferencial hace falta python-chess:\n"
            "    pip install chess",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    return chess


def perft_chess(tablero: object, profundidad: int) -> int:
    """``perft`` de python-chess, para tener el número de referencia."""
    if profundidad == 0:
        return 1
    total = 0
    for movimiento in list(tablero.legal_moves):
        tablero.push(movimiento)
        total += perft_chess(tablero, profundidad - 1)
        tablero.pop()
    return total


# ---------------------------------------------------------------------------
# Los dos modos
# ---------------------------------------------------------------------------

def contra_la_tabla(profundidad: int) -> bool:
    """Compara los perft del modelo con los valores guardados."""
    todo_bien = True
    for nombre, fen, esperados in POSICIONES:
        partida = Partida.desde_fen(fen) if fen else Partida()
        for nivel, esperado in enumerate(esperados[:profundidad], start=1):
            inicio = time.perf_counter()
            obtenido = perft(partida.tablero, partida.turno, nivel)
            bien = obtenido == esperado
            todo_bien = todo_bien and bien
            print(
                f"{nombre:14s} perft({nivel}) = {obtenido:>9}"
                f"  esperado {esperado:>9}  {'OK' if bien else '<<< NO COINCIDE'}"
                f"  ({time.perf_counter() - inicio:5.1f}s)",
                flush=True,
            )
    return todo_bien


def diferencial(profundidad: int) -> bool:
    """Compara el modelo con python-chess, y además nodo a nodo."""
    chess = requiere_chess()
    todo_bien = True
    for nombre, fen, _ in POSICIONES:
        partida = Partida.desde_fen(fen) if fen else Partida()
        tablero = chess.Board(fen) if fen else chess.Board()
        for nivel in range(1, profundidad + 1):
            propio = perft(partida.tablero, partida.turno, nivel)
            de_chess = perft_chess(tablero, nivel)
            if propio == de_chess:
                print(
                    f"{nombre:14s} perft({nivel}) = {propio:>9}  coincide con python-chess",
                    flush=True,
                )
                continue

            todo_bien = False
            print(f"{nombre:14s} perft({nivel}) = {propio:>9}  python-chess dice {de_chess:>9}  <<<")
            for jugada, cuenta in reparto(partida.tablero, partida.turno, nivel).items():
                movimiento = chess.Move.from_uci(jugada)
                if movimiento not in tablero.legal_moves:
                    print(f"    el modelo permite {jugada} y python-chess no")
                    continue
                tablero.push(movimiento)
                esperado = perft_chess(tablero, nivel - 1)
                if cuenta != esperado:
                    print(f"    {jugada}: el modelo {cuenta}, python-chess {esperado}")
                tablero.pop()
    return todo_bien


def fuzz(partidas: int, semilla: int) -> bool:
    """Partidas al azar, comparando las jugadas legales en cada posición.

    El perft de la tabla cubre seis posiciones; esto juega a lo tonto y lo
    comprueba todo, que es donde aparecen los casos raros (jaques dobles,
    en passant que resuelve un jaque, promociones encadenadas).
    """
    chess = requiere_chess()
    generador = random.Random(semilla)
    diferencias: list[str] = []

    def jugar(modelo: Partida, tablero: object, ply: int) -> None:
        if ply > 120 or modelo.esta_terminada() or tablero.is_game_over():
            return
        propias = sorted(
            notacion(movimiento, promocion)
            for movimiento, promocion in jugadas(modelo.tablero, modelo.turno)
        )
        de_chess = sorted(movimiento.uci() for movimiento in tablero.legal_moves)
        if propias != de_chess:
            diferencias.append(
                f"FEN: {tablero.fen()}\n"
                f"  solo en el modelo:  {[m for m in propias if m not in de_chess]}\n"
                f"  solo en la biblioteca: {[m for m in de_chess if m not in propias]}"
            )
            return
        movimiento = generador.choice(list(tablero.legal_moves))
        origen = Posicion(
            chess.square_file(movimiento.from_square), chess.square_rank(movimiento.from_square)
        )
        destino = Posicion(
            chess.square_file(movimiento.to_square), chess.square_rank(movimiento.to_square)
        )
        modelo.mover(origen, destino, promocion_de(movimiento))
        tablero.push(movimiento)
        jugar(modelo, tablero, ply + 1)

    for _ in range(partidas):
        modelo, tablero = Partida(), chess.Board()
        jugar(modelo, tablero, 0)
        if diferencias:
            break

    if not diferencias:
        print(f"{partidas} partidas completas sin ninguna diferencia de jugadas legales.")
        return True
    print("Diferencias encontradas:\n")
    for diferencia in diferencias[:3]:
        print(diferencia)
    return False


# ---------------------------------------------------------------------------

def main() -> int:
    analizador = argparse.ArgumentParser(description="Comprueba las reglas contando jugadas (perft).")
    analizador.add_argument(
        "--diferencial",
        action="store_true",
        help="compara con python-chess en vez de con la tabla guardada",
    )
    analizador.add_argument("--fuzz", type=int, metavar="N", help="juega N partidas al azar comparando jugadas")
    analizador.add_argument("--profundidad", type=int, default=4, help="profundidad máxima (4 por defecto)")
    argumentos = analizador.parse_args()

    if argumentos.fuzz:
        bien = fuzz(argumentos.fuzz, 20260927)
    elif argumentos.diferencial:
        bien = diferencial(argumentos.profundidad)
    else:
        bien = contra_la_tabla(argumentos.profundidad)

    print()
    print("Todo correcto" if bien else "HAY ALGO QUE NO CUADRA")
    return 0 if bien else 1


if __name__ == "__main__":
    raise SystemExit(main())
