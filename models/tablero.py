"""El tablero: qué hay en cada casilla y qué se puede hacer con ello.

Este módulo concentra TODA la lógica de las reglas de movimiento:

* cómo se mueve cada tipo de pieza (salto, deslizamiento, peón, enroque),
* qué casillas threaten las piezas de un color,
* si un rey queda en jaque,
* la legality de una jugada (simulándola sobre una copia del tablero),
* la ejecución de la jugada, incluidas las tres reglas especiales
  (enroque, captura al paso y promoción),
* la lectura y escritura en FEN.

Decisiones de diseño importantes para la revisión:

1. ``_piezas`` es un diccionario ``{Posicion: Pieza}``. Con las 64 casillas
   siempre presentes, un diccionario es más simple y más rápido que una
   matriz con ``None``, y además ``Posicion`` ya es hashable.
2. ``clonar()`` copia el tablero entero. La legalidad de una jugada se
   comprueba aplicándola sobre una copia y mirando si el rey propio queda
   amenazado. Es más lento que un algoritmo optimizado, pero es obviamente
   correcto y se lee muy bien.
3. Los enroques se generan *solo* cuando se piden explícitamente
   (``incluir_enroque=True``). Si se generaran siempre, calcular "casillas
   atacadas" llamaría a ``esta_en_jaque``, que volvería a llamar a
   "casillas atacadas": recursión infinita.
"""

from __future__ import annotations

from models.enums import LETRAS_FEN_INVERSAS, Color, TipoPieza
from models.errores import ErrorAjedrez, MovimientoIlegal
from models.pieza import TIPOS_PROMOCION, Pieza
from models.posicion import (
    DESPLAZAMIENTOS_CABALLO,
    DESPLAZAMIENTOS_REY,
    Movimiento,
    Posicion,
)

# Direcciones de las piezas que se desplazan ("deslizan") en línea recta.
ORTOGONALES = ((0, 1), (1, 0), (0, -1), (-1, 0))

# Direcciones de las piezas que se desplazan en diagonal.
DIAGONALES = ((1, 1), (1, -1), (-1, -1), (-1, 1))

# Opciones de enroque, en tuplas para no repetir código:
#   (columna destino, columna de la torre, casillas que deben estar vacías,
#    casillas del rey que no pueden estar amenazadas)
#   - corto: e1->g1, torre h1, vacías f1 y g1, camino del rey e1-f1-g1
#   - largo: e1->c1, torre a1, vacías b1, c1 y d1, camino del rey e1-d1-c1
OPCIONES_ENROQUE = (
    (6, 7, (5, 6), (4, 5, 6)),
    (2, 0, (1, 2, 3), (4, 3, 2)),
)

# Fila en la que está la primera línea de cada color (la posición inicial).
FILA_INICIAL_PEONES = {Color.BLANCO: 1, Color.NEGRO: 6}


def _desliza_en_rayo(tipo: TipoPieza, columnas: int, filas: int) -> bool:
    """True si la pieza resbala en esa dirección (a lo largo de un rayo).

    Solo se usa con las ocho direcciones del rey, así que hay dos casos y no
    hace falta nada más: una dirección es **ortogonal** (una de las dos
    componentes es cero) o **diagonal** (las dos son distintas de cero). Por
    eso la comprobación es "si una de las dos es cero", en vez de mirar si la
    casilla concreta está en una fila o en una columna.
    """
    if columnas == 0 or filas == 0:
        return tipo in (TipoPieza.TORRE, TipoPieza.DAMA)
    return tipo in (TipoPieza.ALFIL, TipoPieza.DAMA)


class _Legalidad:
    """Lo que se calcula una vez por posición y luego se reutiliza.

    ``es_legal`` funciona clonando el tablero entero y mirando si el rey propio
    queda amenazado, y eso hay que hacerlolo por cada jugada candidata: con 30
    jugadas son 30 clones. Almost todo ese trabajo es el mismo para todas las
    jugadas de la posición, y esto es la parte que se puede calcular una vez:

    * ``atacadas``: las casillas que amenazan las piezas del rival. Es
      exactamente lo que devuelve ``casillas_atacadas_por``, y da tanto para
      saber si estamos en jaque como para comprobar el camino del rey en el
      enroque.
    * ``en_jaque``: si la casilla de nuestro rey está en ese conjunto.
    * ``clavadas``: qué piezas propias son el **único** bloqueo entre nuestro
      rey y una pieza rival que resbala (el "pin" de los manuales en inglés).

    Con esto, la jugada de una pieza que no está clavada se puede declarar legal
    sin clonar nada: si no está clavada es que no es el bloqueo de ningún rayo
    de jaque, así que al moverla no puede aparecer un ataque nuevo contra
    nuestro rey.
    """

    __slots__ = ("color", "rey", "atacadas", "en_jaque", "clavadas")

    def __init__(
        self,
        color: Color,
        rey: Posicion,
        atacadas: set[Posicion],
        clavadas: dict[Posicion, tuple[int, int]],
    ) -> None:
        self.color = color
        self.rey = rey
        self.atacadas = atacadas
        self.en_jaque = rey in atacadas
        self.clavadas = clavadas


class Tablero:
    """Tablero de 8x8: piezas, generación de movimientos y detección de jaque."""

    def __init__(
        self,
        piezas: dict[Posicion, Pieza] | None = None,
        derechos_enroque: set[str] | None = None,
        ultima_jugada: Movimiento | None = None,
    ) -> None:
        # Diccionario interno: casilla -> pieza. Se accede siempre a través de
        # `obtener`/`colocar`/`retirar` para no perder la validación.
        self._piezas: dict[Posicion, Pieza] = {}
        # Derechos de enroque que siguen vigentes: "K", "Q" (blancas) y
        # "k", "q" (negras), igual que en el FEN. Son datos de la partida, no
        # derivables de las piezas: si la torre se movió y volvió, ya no se
        # puede enrocar aunque la torre siga en su casilla.
        self.derechos_enroque: set[str] = set(derechos_enroque or ())
        # Última jugada jugada: se necesita para la captura al paso.
        self.ultima_jugada = ultima_jugada
        for pieza in (piezas or {}).values():
            self.colocar(pieza)

    # ------------------------------------------------------------------
    # Constructores
    # ------------------------------------------------------------------

    @classmethod
    def posicion_inicial(cls) -> Tablero:
        """Crea el tablero con la disposición inicial estándar.

        Se construye el diccionario y se pasa al constructor en vez de colocar
        pieza a pieza, para no disparar la validación de casillas ocupadas
        32 veces.
        """
        piezas: dict[Posicion, Pieza] = {}
        # Orden de las piezas mayores en la primera fila: torre, caballo,
        # alfil, dama, rey, alfil, caballo, torre.
        primera_fila = (
            (TipoPieza.TORRE, 0),
            (TipoPieza.CABALLO, 1),
            (TipoPieza.ALFIL, 2),
            (TipoPieza.DAMA, 3),
            (TipoPieza.REY, 4),
            (TipoPieza.ALFIL, 5),
            (TipoPieza.CABALLO, 6),
            (TipoPieza.TORRE, 7),
        )
        for color in (Color.BLANCO, Color.NEGRO):
            fila = 0 if color is Color.BLANCO else 7
            for tipo, columna in primera_fila:
                posicion = Posicion(columna, fila)
                piezas[posicion] = Pieza(color, tipo, posicion)
            fila_peones = FILA_INICIAL_PEONES[color]
            for columna in range(8):
                posicion = Posicion(columna, fila_peones)
                piezas[posicion] = Pieza(color, TipoPieza.PEON, posicion)
        return cls(piezas, {"K", "Q", "k", "q"})

    @classmethod
    def desde_fen(cls, fen: str, derechos_enroque: set[str] | None = None) -> Tablero:
        """Crea un tablero a partir de la parte de colocación de un FEN.

        Un FEN completo es ``piezas turno enroque al-paso medio-movimiento
        jugada``; aquí solo se interpreta el primer campo. Los derechos de
        enroque se reciben aparte porque no se deducen de las piezas.
        """
        if not isinstance(fen, str) or not fen.strip():
            raise ErrorAjedrez("El FEN no puede estar vacío.")
        colocacion = fen.strip().split(" ")[0]
        filas = colocacion.split("/")
        if len(filas) != 8:
            raise ErrorAjedrez("El FEN debe describir las 8 filas del tablero.")
        piezas: dict[Posicion, Pieza] = {}
        # El FEN empieza por la fila 8, así que se recorre la lista al revés.
        for indice, fila in enumerate(reversed(filas)):
            columna = 0
            for simbolo in fila:
                # Un dígito indica cuántas casillas vacías hay: "3" = tres
                # casillas vacías antes de la siguiente pieza.
                if simbolo.isdigit():
                    columna += int(simbolo)
                    continue
                tipo = LETRAS_FEN_INVERSAS.get(simbolo.lower())
                if tipo is None or columna > 7:
                    raise ErrorAjedrez(f"Contenido inválido en el FEN: {simbolo!r}.")
                # Mayúscula = blancas, minúscula = negras.
                color = Color.BLANCO if simbolo.isupper() else Color.NEGRO
                posicion = Posicion(columna, indice)
                piezas[posicion] = Pieza(color, tipo, posicion)
                columna += 1
            if columna != 8:
                raise ErrorAjedrez("Cada fila del FEN debe describir 8 casillas.")
        return cls(piezas, set(derechos_enroque or ()))

    def clonar(self) -> Tablero:
        """Copia independiente del tablero, para simular jugadas.

        Se clonan también los derechos de enroque y la última jugada, porque
        la simulación necesita ver exactamente el mismo estado.
        """
        return Tablero(
            {posicion: pieza.con_posicion(pieza.posicion) for posicion, pieza in self._piezas.items()},
            set(self.derechos_enroque),
            self.ultima_jugada,
        )

    # ------------------------------------------------------------------
    # Acceso básico al contenido
    # ------------------------------------------------------------------

    def colocar(self, pieza: Pieza) -> None:
        """Coloca una pieza en su casilla rechazando casillas ocupadas."""
        if self.en_juego(pieza.posicion):
            raise ErrorAjedrez(f"La casilla {pieza.posicion.notacion} ya está ocupada.")
        self._piezas[pieza.posicion] = pieza

    def retirar(self, posicion: Posicion) -> Pieza | None:
        """Retira la pieza de una casilla y la devuelve, o ``None`` si estaba vacía."""
        return self._piezas.pop(posicion, None)

    def obtener(self, posicion: Posicion) -> Pieza | None:
        """Pieza que ocupa una casilla, o ``None`` si está vacía."""
        return self._piezas.get(posicion)

    def en_juego(self, posicion: Posicion) -> bool:
        """Indica si hay alguna pieza en la casilla."""
        return posicion in self._piezas

    def limpiar(self) -> None:
        """Vacía el tablero y reinicia los derechos de enroque."""
        self._piezas.clear()
        self.derechos_enroque.clear()
        self.ultima_jugada = None

    def piezas(self, color: Color | None = None) -> list[Pieza]:
        """Piezas del tablero, filtradas por color si se indica."""
        return [pieza for pieza in self._piezas.values() if color is None or pieza.color is color]

    def rey_de(self, color: Color) -> Pieza | None:
        """Rey de un color, o ``None`` si no está en el tablero."""
        for pieza in self._piezas.values():
            if pieza.color is color and pieza.tipo is TipoPieza.REY:
                return pieza
        return None

    # ------------------------------------------------------------------
    # Amenazas y jaque
    # ------------------------------------------------------------------

    def casillas_atacadas_por(self, color: Color) -> set[Posicion]:
        """Casillas amenazadas por las piezas de un color.

        Se usa el generador de destinos *sin* enroques: un enroque no es un
        ataque (mueve al rey, no threaten), y además generar enroques aquí
        produciría recursión infinita.

        Detalle de reglas: una pieza se considera que amenaza una casilla
        aunque no pueda capturarla porque dejaría a su propio rey en jaque
        (artículo 3.1.3 de los reglamentos). Por eso aquí no se comprueba la
        seguridad del rey atacante, solo la geometría.
        """
        atacadas: set[Posicion] = set()
        for pieza in self.piezas(color):
            atacadas.update(self._destinos_de(pieza))
        return atacadas

    def es_ataqueada(self, posicion: Posicion, por: Color) -> bool:
        """Indica si una casilla está amenazada por el color indicado."""
        return posicion in self.casillas_atacadas_por(por)

    def esta_en_jaque(self, color: Color) -> bool:
        """Indica si el rey de un color está amenazado."""
        rey = self.rey_de(color)
        if rey is None:
            raise ErrorAjedrez(f"No hay rey {color.value} en el tablero.")
        return self.es_ataqueada(rey.posicion, color.contrario)

    # ------------------------------------------------------------------
    # Preparación de la legalidad (ataque por ataque, una vez por posición)
    # ------------------------------------------------------------------

    def _preparar_legalidad(self, color: Color) -> _Legalidad | None:
        """Reúne en un objeto lo que hace falta para filtrar jugadas.

        Se llama una vez por posición, antes de generar las jugadas del color,
        y devuelve ``None`` si el color no tiene rey en el tablero (en ese caso
        no hay nada que optimizar y todo se resuelve por la vía lenta, que es
        la que sabe dar la respuesta cuando no hay rey).

        El coste es de un ``casillas_atacadas_por`` (O(piezas)) más ocho
        rayos desde el rey, frente a los ~30 clones que hacía falta antes.
        """
        rey = self.rey_de(color)
        if rey is None:
            return None
        atacadas = self.casillas_atacadas_por(color.contrario)
        return _Legalidad(color, rey.posicion, atacadas, self._piezas_clavadas(color, rey.posicion))

    def _piezas_clavadas(self, color: Color, rey: Posicion) -> dict[Posicion, tuple[int, int]]:
        """Piezas propias cuya salida dejaría al rey en jaque.

        Una pieza está **clavada** cuando es el único bloqueo entre el rey y una
        pieza rival que resbala por esa misma línea. Si la mueve, el rey se
        queda a tiro.

        Cómo se detecta, por cada una de las ocho direcciones del rey:

        1. se busca la **primera** pieza del rayo,
        2. si no es nuestra, no hay nada que hacer con esa dirección (si fuera
           una rival que resbala, estaríamos en jaque y eso lo mira otro sitio),
        3. si es nuestra, se busca la **segunda** pieza del rayo,
        4. esa segunda pieza es la que importa: si es rival y resbala por esa
           dirección, la primera estaba clavada. Si es nuestra, hay un tercer
           bloqueo después y esta dirección no ata a nadie.

        Ojo con por qué se necesitan **dos** casillas y no una: que haya una
        pieza propia en el rayo no la convierte en clavija. Solo la ata si
        detrás no hay ningún otro bloqueo y lo que viene es una rival que
        resbala.

        El valor del diccionario es la dirección del rayo (``(columnas, filas)``),
        que es lo que hace falta después para preguntar si una jugada se sale
        de la línea.
        """
        clavadas: dict[Posicion, tuple[int, int]] = {}
        for columnas, filas in DESPLAZAMIENTOS_REY:
            primera, segunda = self._dos_primeras_en_rayo(rey, columnas, filas)
            if primera is None:
                continue
            if self._piezas[primera].color is not color:
                continue
            if segunda is None:
                continue
            rival = self._piezas[segunda]
            if rival.color is color:
                continue
            if _desliza_en_rayo(rival.tipo, columnas, filas):
                clavadas[primera] = (columnas, filas)
        return clavadas

    def _dos_primeras_en_rayo(
        self, desde: Posicion, columnas: int, filas: int
    ) -> tuple[Posicion | None, Posicion | None]:
        """Las dos primeras piezas que hay en una dirección, y ``None`` si faltan.

        Se usa para la clavada. No baja por un rayo entero como quien busca
        destinos, sino que se para en la segunda pieza: para saber si la
        primera está clavada no hace falta nada más allá de la segunda.
        """
        destino = desde.desplazar(columnas, filas)
        primera = None
        while destino is not None:
            if destino in self._piezas:
                if primera is None:
                    primera = destino
                else:
                    return primera, destino
            destino = destino.desplazar(columnas, filas)
        return primera, None

    # ------------------------------------------------------------------
    # Generación de movimientos
    # ------------------------------------------------------------------

    def destinos_de(self, posicion: Posicion) -> list[Posicion]:
        """Destinos geométricos de la pieza en una casilla (pueden ser ilegales)."""
        pieza = self.obtener(posicion)
        if pieza is None:
            return []
        return self._destinos_de(pieza)

    def movimientos_de(self, posicion: Posicion) -> list[Movimiento]:
        """Movimientos legales de la pieza que ocupa una casilla.

        Es lo que usa la vista para resaltar a dónde puede ir la pieza que el
        jugador acaba de seleccionar.
        """
        pieza = self.obtener(posicion)
        if pieza is None:
            return []
        contexto = self._preparar_legalidad(pieza.color)
        candidatos = [
            Movimiento(posicion, destino)
            for destino in self._destinos_de(pieza, incluir_enroque=True)
        ]
        return [
            movimiento
            for movimiento in candidatos
            if self._es_legal_con_contexto(movimiento, contexto)
        ]

    def movimientos_legales(self, color: Color) -> list[Movimiento]:
        """Todos los movimientos legales disponibles para un color.

        Se usa para validar lo que escribe el jugador y para detectar jaque
        mate y ahogado (si no hay ningún movimiento legal, la partida terminó).

        El análisis de la posición (ataques del rival y piezas clavadas) se hace
        **una vez** y se reutiliza para todas las jugadas, en vez de repetirlo
        en cada candidata. Las jugadas que no se pueden resolver así (rey, jaque,
        enroque y captura al paso) siguen yendo por la simulación con clon.
        """
        resultado = []
        contexto = self._preparar_legalidad(color)
        for pieza in self.piezas(color):
            for destino in self._destinos_de(pieza, incluir_enroque=True):
                movimiento = Movimiento(pieza.posicion, destino)
                if self._es_legal_con_contexto(movimiento, contexto):
                    resultado.append(movimiento)
        return resultado

    def _es_legal_con_contexto(self, movimiento: Movimiento, contexto: _Legalidad | None) -> bool:
        """Si la jugada es legal, reutilizando lo que ya se calculó por posición.

        Es el camino rápido de ``es_legal``, y la respuesta tiene que ser
        **exactamente la misma**. La diferencia es de dónde sale: en vez de
        clonar el tablero y recomputar todos los ataques, usa el análisis de la
        posición que ya hizo ``_preparar_legalidad``.

        Lo que se decide aquí sin clonar, y por qué es correcto:

        * **Una pieza que no está clavada se puede mover.** Si no está clavada,
          no es el único bloqueo entre nuestro rey y ninguna pieza rival que
          resbala, así que al moverla no puede quedar descubierto un ataque
          contra el rey. Tampoco puede aparecer un ataque nuevo capturing: si la
          pieza captura a una rival, lo único que desaparece del tablero es una
          atacante, nunca aparece una.

        Y lo que **no** se decide aquí, porque se delega en ``es_legal`` (la
        simulación con clon) para no perder exactitud:

        * **El movimiento del rey**, con o sin enroque. Al quitar el rey de su
          casilla pueden desaparecer attackers que lo cubrían, así que la
          casilla de destino hay que mirarla sobre el tablero ya movido.
        * **Cualquier jugada con el rey en jaque.** En jaque solo vale mover el
          rey o tapar/capturar el atacante, y decidirlo sin simular es un
          segundo problema distinto. Las posiciones con jaque son una
          minoría, así que el coste no importa.
        * **La captura al paso**, porque es la única jugada capaz de descubrir
          el jaque sobre un rayo que **no** pasa por la pieza que se mueve: al
          retirar el peón capturado disappears un bloque en una fila en la que
          puede haber los dos reyes alineados. Se simula, que es lo correcto.
        """
        if contexto is None:
            return self.es_legal(movimiento)
        pieza = self.obtener(movimiento.origen)
        if pieza is None or movimiento.origen == movimiento.destino:
            return False
        objetivo = self.obtener(movimiento.destino)
        if objetivo is not None and objetivo.color is pieza.color:
            return False
        if objetivo is not None and objetivo.tipo is TipoPieza.REY:
            return False
        if pieza.tipo is TipoPieza.REY:
            return self.es_legal(movimiento)
        if contexto.en_jaque:
            return self.es_legal(movimiento)
        if self._es_captura_al_paso_de(movimiento):
            return self.es_legal(movimiento)
        if movimiento.origen in contexto.clavadas:
            return self._sigue_en_el_rayo(contexto, movimiento)
        return True

    def _sigue_en_el_rayo(self, contexto: _Legalidad, movimiento: Movimiento) -> bool:
        """True si el destino sigue en la línea por la que la pieza está clavada.

        "Seguir en la línea" se comprueba con aritmética, no mirando si el
        destino cae en la misma fila, columna o diagonal que el rey:

        * **colinealidad**: el destino tiene que estar en la recta que pasa por
          el rey con esa dirección, no en una cualquiera que vaya para el mismo
          lado. Con el rey en e8 y la pieza clavada en d7 (rayo hacia el
          NO-OESTE, hacia b5), la casilla d6 va "hacia abajo y hacia la
          izquierda" pero **no** está en esa diagonal, así que salir ahí sí
          descubre el jaque. Comparar solo los signos de las diferencias no
          serviría: daría por buena la jugada.
        * **sentido**: estar en la misma recta no basta, el destino tiene que
          estar hacia el mismo lado del rey que el rayo, no al revés.

        Las dos juntas son el producto vectorial (que vale 0 solo si son
        colineales) y el producto escalar (que dice si van en el mismo sentido).
        """
        columnas, filas = contexto.clavadas[movimiento.origen]
        delta_columnas = movimiento.destino.columna - contexto.rey.columna
        delta_filas = movimiento.destino.fila - contexto.rey.fila
        if delta_columnas * filas != delta_filas * columnas:
            return False
        return delta_columnas * columnas + delta_filas * filas > 0

    def _es_captura_al_paso_de(self, movimiento: Movimiento) -> bool:
        """True si esta jugada es una captura al paso.

        Es la misma condición que usa ``_aplicar`` para decidir si tiene que
        retirar el peón de al lado: el destino está vacío **y** la captura al
        paso es legal con la casilla de siempre. Las dos piezas, la que se
        mueve y la víctima, se escriben siempre en casillas contiguas, así que
        para el peón que se mueve esto se puede comprobar sin llegar a aplicar
        la jugada.
        """
        pieza = self.obtener(movimiento.origen)
        if pieza is None or pieza.tipo is not TipoPieza.PEON:
            return False
        if self.en_juego(movimiento.destino):
            return False
        return self._es_captura_al_paso(pieza, movimiento.destino)

    def es_legal(self, movimiento: Movimiento) -> bool:
        """Indica si el movimiento existe y no deja al rey propio en jaque.

        Antes de nada se descarta lo que nunca es una jugada, ni siquiera
        geométricamente: mover a una casilla vacía desde una casilla vacía,
        capturar una pieza propia o capturar un rey.

        Después son dos comprobaciones, y las dos hacen falta:

        1. Que el destino esté entre los destinos *geométricos* de la pieza.
           Sin esto, un peón podría "saltar" tres casillas: al simular la
           jugada no hay rey en jaque, así que el movimiento se aceptaría.
           (Cuando quien llama ya ha generado los candidatos con
           ``_destinos_de`` la comprobación es redundante, pero es el precio
           de que ``aplicar`` pueda validar por su cuenta.)
        2. Que al aplicarlo el rey propio no quede amenazado. Es la forma más
           simple de implementar la regla "no puedes hacer una jugada que te
           deje en jaque" y cubre de paso los casos difíciles (rayos
           descubiertos, clavadas, etc.).

        Criterio para la segunda: se aplica el movimiento sobre un *clon* del
        tablero y se comprueba que el rey propio no quede amenazado.
        """
        pieza = self.obtener(movimiento.origen)
        if pieza is None or movimiento.origen == movimiento.destino:
            return False
        objetivo = self.obtener(movimiento.destino)
        # No se puede capturar una pieza propia.
        if objetivo is not None and objetivo.color is pieza.color:
            return False
        # No se puede capturar un rey. En un juego real la partida ya habría
        # terminado en jaque mate antes de llegar aquí, así que la jugada ni
        # siquiera se ofrecería. Se rechaza igualmente para que el modelo no
        # tenga un camino que produzca una posición imposible (con dos reyes
        # del mismo color o sin rey) y para que nadie espere ese final.
        if objetivo is not None and objetivo.tipo is TipoPieza.REY:
            return False
        # El destino tiene que ser uno de los que la pieza puede alcanzar. Los
        # enroques se piden explícitamente porque comproban el jaque propio, y
        # aquí se está comprobando justo eso.
        if movimiento.destino not in self._destinos_de(pieza, incluir_enroque=True):
            return False
        simulacion = self.clonar()
        simulacion._aplicar(movimiento)
        rey = simulacion.rey_de(pieza.color)
        if rey is None:
            return False
        return not simulacion.es_ataqueada(rey.posicion, pieza.color.contrario)

    # ------------------------------------------------------------------
    # Ejecución de jugadas
    # ------------------------------------------------------------------

    def aplicar(self, movimiento: Movimiento, promocion: TipoPieza | None = None) -> Pieza | None:
        """Ejecuta un movimiento legal y devuelve la pieza capturada."""
        if not self.es_legal(movimiento):
            raise MovimientoIlegal(f"Movimiento no permitido: {movimiento.notacion}.")
        return self._aplicar(movimiento, promocion)

    def _aplicar(self, movimiento: Movimiento, promocion: TipoPieza | None = None) -> Pieza | None:
        """Ejecuta el movimiento sin validar la legalidad.

        Se separa de ``aplicar`` porque las simulaciones de ``es_legal``
        necesitan ejecutar jugadas que no han sido validadas todavía. El
        único requisito es que el movimiento sea *geométricamente* posible.
        """
        pieza = self.obtener(movimiento.origen)
        if pieza is None:
            raise MovimientoIlegal(f"No hay pieza en {movimiento.origen.notacion}.")
        # La promoción se decide ANTES de retirar el peón: si se comprobara
        # después, la pieza ya no estaría en el origen y nunca se detectaría.
        promociona = pieza.tipo is TipoPieza.PEON and movimiento.destino.fila in (0, 7)
        if promociona and promocion is not None and promocion not in TIPOS_PROMOCION:
            raise MovimientoIlegal("La promoción debe ser a dama, torre, alfil o caballo.")
        capturada = self.retirar(movimiento.destino)
        # Captura al paso: la casilla de destino está vacía y la víctima está
        # justo al lado, en la fila de la que parte el peón que captura.
        if capturada is None and self._es_captura_al_paso(pieza, movimiento.destino):
            capturada = self.retirar(Posicion(movimiento.destino.columna, movimiento.origen.fila))
        self.retirar(movimiento.origen)
        tipo = pieza.tipo
        if promociona:
            # Sin promoción explícita se promueve a dama (regla por defecto).
            tipo = promocion if promocion is not None else TipoPieza.DAMA
        self.colocar(Pieza(pieza.color, tipo, movimiento.destino))
        # En el enroque el rey y la torre se mueven a la vez.
        if movimiento.es_enroque and pieza.tipo is TipoPieza.REY:
            self._desplazar_torre_enroque(movimiento)
        # Se recuerda la jugada para que el siguiente turno pueda capturar al paso.
        self.ultima_jugada = movimiento
        return capturada

    def _desplazar_torre_enroque(self, movimiento: Movimiento) -> None:
        """Mueve la torre a la casilla correcta al enrocar al rey."""
        torre = self.retirar(Posicion(7 if movimiento.destino.columna == 6 else 0, movimiento.origen.fila))
        if torre is None:
            return
        columna_destino = 5 if movimiento.destino.columna == 6 else 3
        self.colocar(torre.con_posicion(Posicion(columna_destino, movimiento.origen.fila)))

    # ------------------------------------------------------------------
    # Reglas especiales
    # ------------------------------------------------------------------

    def _es_captura_al_paso(self, pawn: Pieza, destino: Posicion) -> bool:
        """Indica si un peón puede capturar al paso hacia una casilla diagonal vacía.

        Se puede capturar al paso solo si, inmediatamente antes, el rival movió
        un peón dos casillas y dejó su peón justo al lado del nuestro. Todas
        esas condiciones se comprueban aquí:

        0. **la pieza que se mueve es un peón** (y no cualquier otra pieza),
        1. la casilla destino es la sexta (para blancas) o la tercera (negras),
        2. el destino es diagonal a la casilla del peón que captura,
        3. el peón está en la fila inmediatamente anterior a la del destino,
        4. la última jugada fue un avance de peón de dos casillas,
        5. ese peón acabó en la casilla contigua a nuestro peón,
        6. en esa casilla hay efectivamente un peón enemigo.

        La condición 0 parece redundante porque el método se llama desde
        ``_destinos_de_peon``, pero ``_aplicar`` también lo llama y ahí la pieza
        que se mueve es la que sea. Sin esa comprobación, cualquier pieza que
        se moviese en diagonal a la casilla de la posible captura al paso se
        llevaría por delante un peón que no está en su camino: la casilla de la
        víctima se calcula como ``(columna del destino, fila del origen)``, y
        para un rey o un alfil cualquiera esa cuenta da una casilla
        perfectamente válida.
        """
        if pawn.tipo is not TipoPieza.PEON:
            return False
        if self.ultima_jugada is None:
            return False
        fila_destino = 5 if pawn.color is Color.BLANCO else 2
        if destino.fila != fila_destino:
            return False
        if abs(destino.columna - pawn.posicion.columna) != 1:
            return False
        if abs(destino.fila - pawn.posicion.fila) != 1:
            return False
        previa = self.ultima_jugada
        if abs(previa.destino.fila - previa.origen.fila) != 2:
            return False
        casilla_victima = Posicion(destino.columna, pawn.posicion.fila)
        if previa.destino != casilla_victima:
            return False
        victima = self.obtener(casilla_victima)
        return (
            victima is not None
            and victima.tipo is TipoPieza.PEON
            and victima.color is not pawn.color
        )

    def _destinos_de(self, pieza: Pieza, incluir_enroque: bool = False) -> list[Posicion]:
        """Casillas destino de una pieza según su tipo de movimiento.

        Cada tipo de pieza es una estrategia distinta:
        * peón: avanza recto y captura en diagonal, con casos especiales,
        * caballo y rey: "saltador" (destinos fijos),
        * torre y alfil: "deslizador" (repite el paso hasta toparse con algo),
        * dama: las dos cosas a la vez.
        """
        if pieza.tipo is TipoPieza.PEON:
            return self._destinos_de_peon(pieza)
        if pieza.tipo is TipoPieza.CABALLO:
            return self._destinos_de_saltador(pieza, DESPLAZAMIENTOS_CABALLO)
        if pieza.tipo is TipoPieza.ALFIL:
            return self._destinos_de_deslizador(pieza, DIAGONALES)
        if pieza.tipo is TipoPieza.TORRE:
            return self._destinos_de_deslizador(pieza, ORTOGONALES)
        if pieza.tipo is TipoPieza.DAMA:
            return self._destinos_de_deslizador(pieza, DIAGONALES + ORTOGONALES)
        # El rey se mueve como un saltador y, si se pide, puede enrocar.
        destinos = self._destinos_de_saltador(pieza, DESPLAZAMIENTOS_REY)
        if incluir_enroque:
            destinos += self._destinos_de_enroque(pieza)
        return destinos

    def _destinos_de_peon(self, pieza: Pieza) -> list[Posicion]:
        """Destinos de un peón: avance recto y capturas diagonales.

        El peón es la única pieza que no se mueve como "saltador" ni como
        "deslizador": avanza recto, captura en diagonal y solo puede avanzar dos
        casillas desde su fila inicial.
        """
        direccion = 1 if pieza.color is Color.BLANCO else -1
        fila_inicial = FILA_INICIAL_PEONES[pieza.color]
        destinos = []
        # Avance de una casilla, solo si está vacía.
        avance = pieza.posicion.desplazar(0, direccion)
        if avance is not None and not self.en_juego(avance):
            destinos.append(avance)
            # Avance de dos casillas desde la fila inicial, si el camino está libre.
            if pieza.posicion.fila == fila_inicial:
                doble = pieza.posicion.desplazar(0, 2 * direccion)
                if doble is not None and not self.en_juego(doble):
                    destinos.append(doble)
        # Capturas diagonales: solo si hay enemigo, o si es captura al paso.
        for columnas in (-1, 1):
            diagonal = pieza.posicion.desplazar(columnas, direccion)
            if diagonal is None:
                continue
            objetivo = self.obtener(diagonal)
            if objetivo is None:
                if self._es_captura_al_paso(pieza, diagonal):
                    destinos.append(diagonal)
            elif objetivo.color is not pieza.color:
                destinos.append(diagonal)
        return destinos

    def _destinos_de_saltador(self, pieza: Pieza, desplazamientos) -> list[Posicion]:
        """Destinos de una pieza que "salta" a casillas concretas (rey y caballo)."""
        destinos = []
        for columnas, filas in desplazamientos:
            destino = pieza.posicion.desplazar(columnas, filas)
            if destino is None:
                continue
            objetivo = self.obtener(destino)
            # Se puede saltar a una casilla vacía o a una con pieza enemiga.
            if objetivo is None or objetivo.color is not pieza.color:
                destinos.append(destino)
        return destinos

    def _destinos_de_deslizador(self, pieza: Pieza, direcciones) -> list[Posicion]:
        """Destinos de una pieza que se desliza (torre, alfil, dama).

        Se avanza casilla a casilla en cada dirección y se para en el primer
        obstáculo: si hay pieza enemiga se puede capturar y ahí termina; si es
        propia, no se puede seguir.
        """
        destinos = []
        for columnas, filas in direcciones:
            destino = pieza.posicion.desplazar(columnas, filas)
            while destino is not None:
                objetivo = self.obtener(destino)
                if objetivo is None:
                    destinos.append(destino)
                else:
                    if objetivo.color is not pieza.color:
                        destinos.append(destino)
                    break
                destino = destino.desplazar(columnas, filas)
        return destinos

    def _destinos_de_enroque(self, rey: Pieza) -> list[Posicion]:
        """Destinos de enroque del rey, si cumple todas las condiciones."""
        # No se puede enrocar estando en jaque.
        if self.esta_en_jaque(rey.color):
            return []
        fila = 0 if rey.color is Color.BLANCO else 7
        # Solo desde la casilla inicial del rey.
        if rey.posicion != Posicion(4, fila):
            return []
        destinos = []
        for columna_destino, columna_torre, casillas_vacias, camino_rey in OPCIONES_ENROQUE:
            if not self._tiene_derecho_enroque(rey.color, columna_destino):
                continue
            if not self._tiene_pieza(Posicion(columna_torre, fila), TipoPieza.TORRE, rey.color):
                continue
            # Las casillas entre el rey y su destino deben estar vacías
            # (la casilla del rey se excluye: ya está ocupada por el rey).
            if any(self.en_juego(Posicion(columna, fila)) for columna in casillas_vacias):
                continue
            # El rey no puede pasar por una casilla amenazada.
            if any(self.es_ataqueada(Posicion(columna, fila), rey.color.contrario) for columna in camino_rey):
                continue
            destinos.append(Posicion(columna_destino, fila))
        return destinos

    def _tiene_derecho_enroque(self, color: Color, columna_destino: int) -> bool:
        """Comprueba si el color conserva el derecho de ese enroque."""
        base = "K" if columna_destino == 6 else "Q"
        derecho = base if color is Color.BLANCO else base.lower()
        return derecho in self.derechos_enroque

    def _tiene_pieza(self, posicion: Posicion, tipo: TipoPieza, color: Color) -> bool:
        """True si en esa casilla hay exactamente esa pieza de ese color."""
        pieza = self.obtener(posicion)
        return pieza is not None and pieza.tipo is tipo and pieza.color is color

    # ------------------------------------------------------------------
    # Utilidades y presentación
    # ------------------------------------------------------------------

    def clave(self) -> str:
        """Cadena que identifica la posición, para detectar repeticiones.

        Dos posiciones con la misma clave tienen exactamente las mismas
        piezas en las mismas casillas, así que la clave sirve tanto para
        detectar la repetición triple (tablas) como para guardar una posición
        en caché sin necesidad de objetos.
        """
        casillas = []
        for fila in range(7, -1, -1):
            for columna in range(8):
                pieza = self.obtener(Posicion(columna, fila))
                casillas.append(pieza.simbolo if pieza is not None else ".")
        return "".join(casillas)

    def to_dict(self) -> dict:
        """Serializa el tablero (usada por la persistencia).

        Las piezas se guardan como lista, no como diccionario, porque las
        claves (``Posicion``) no son serializables a JSON y la lista es más
        legible para quien abra el archivo a mano.
        """
        return {
            "piezas": [pieza.to_dict() for pieza in self.piezas()],
            "derechos_enroque": sorted(self.derechos_enroque),
            "ultima_jugada": self.ultima_jugada.to_dict() if self.ultima_jugada else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Tablero:
        """Reconstruye el tablero desde su forma serializada."""
        piezas = [Pieza.from_dict(datos) for datos in data.get("piezas", [])]
        return cls(
            {pieza.posicion: pieza for pieza in piezas},
            set(data.get("derechos_enroque", [])),
            Movimiento.from_dict(data["ultima_jugada"]) if data.get("ultima_jugada") else None,
        )

    def __str__(self) -> str:
        """Dibuja el tablero en texto; lo usa la vista y los tests."""
        filas = []
        for fila in range(7, -1, -1):
            casillas = [
                self.obtener(Posicion(columna, fila)).simbolo
                if self.en_juego(Posicion(columna, fila))
                else "·"
                for columna in range(8)
            ]
            filas.append(f"{fila + 1} {' '.join(casillas)}")
        # Última línea: las letras de las columnas, para poder leer coordenadas.
        filas.append(f"  {' '.join('abcdefgh')}")
        return "\n".join(filas)
