"""``Partida``: la partida en curso, es decir, el tablero **más** el estado.

Hasta aquí (``enums``, ``errores``, ``posicion``, ``pieza``, ``tablero``) todo lo
que se ha modelado son hechos del tablero: qué hay en cada casilla y qué
permiten las reglas. Pero un juego de ajedrez no es solo el tablero; además hay
un *estado de la partida* que depende de la historia:

* de quién es el turno,
* si la partida ya terminó y por qué (jaque mate, ahogado, tablas, abandono),
 * cuántas jugadas van y cuántas han pasado sin captura ni movimiento de peón,
* qué posiciones se han repetido ya.

Todo eso vive en esta clase. La separación es la misma que en el resto del
proyecto: aquí **no** hay un solo ``input()`` ni un solo ``print()``; lo único
que se hace es recibir datos y devolver objetos o excepciones.

Jerarquía de dependencias del modelo (cada módulo solo importa del anterior)::

    errores  ->  enums  ->  posicion / pieza  ->  tablero  ->  partida

Por eso ``partida.py`` es el último: es el módulo que conoce a todos los demás
y, aun así, no conoce a nadie.
"""

from __future__ import annotations

from models.enums import Color, EstadoPartida, TipoPieza
from models.errores import ErrorAjedrez, MovimientoIlegal, PartidaTerminada
from models.pieza import LETRAS_PROMOCION, TIPOS_PROMOCION, Pieza
from models.posicion import Movimiento, Posicion
from models.tablero import Tablero

# ---------------------------------------------------------------------------
# Constantes de las reglas de fin de partida.
#
# Las reglas dicen cuántas jugadas sin "avance" (captura o movimiento de
# peón) permiten declarar el empate: la regla de las 50/movimiento es
# normalmente 100 *medio*-movimientos, porque cada jugada de un jugador son
# dos medio-movimientos. Se escribe así para que el número signifique algo
# legible: 100 medias jugadas = 50 jugadas completas.
# ---------------------------------------------------------------------------

MEDIO_MOVIMIENTOS_PARA_TABLAS = 100

# Repeticiones de la misma posición (piezas + turno) que declaran tablas.
REPETICIONES_PARA_TABLAS = 3

# FEN de la posición inicial estándar. Se usa como ancla por defecto cuando
# se carga una partida guardada por una versión del programa que no guardaba el
# ancla (ver ``_fen_inicial``): es lo único que se puede suponer de una partida
# cuyo punto de partida no se conoce.
FEN_INICIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _jugada_al_paso(casilla: Posicion) -> Movimiento:
    """Reconstruye la jugada doble de peón a la que pertenece una casilla "al paso".

    El FEN guarda, en su cuarto campo, la casilla *por la que puede pasar* un
    peón que acaba de avanzar dos casillas (por ejemplo ``e3``). Esa casilla es
    la que ocupa el peón que se acaba de mover, así que el movimiento que la
    produjo es exactamente el inverso de un salto de dos filas desde la fila
    de partida.

    Sirve para que al recargar una partida desde un FEN siga siendo posible la
    captura al paso: sin este movimiento previo, ``Tablero`` no sabría que el
    peón enemigo acaba de hacer un avance doble y no ofrecería la captura.
    """
    # Fila 3 (índice 2): el peón blanco venía de la fila 2 (índice 1).
    if casilla.fila == 2:
        return Movimiento(Posicion(casilla.columna, 1), Posicion(casilla.columna, 3))
    # Fila 6 (índice 5): el peón negro venía de la fila 7 (índice 6).
    if casilla.fila == 5:
        return Movimiento(Posicion(casilla.columna, 6), Posicion(casilla.columna, 4))
    raise ErrorAjedrez(f"La casilla al paso {casilla.notacion} no corresponde a una jugada doble.")


class Partida:
    """Partida de ajedrez: tablero, turno, historial y estado del resultado.

    Es una clase "rica" y no un simple contenedor de datos porque *es* donde
    viven las reglas que dependen del estado. Un tablero por sí solo no puede
    saber si la partida terminó: necesita el historial (para las repeticiones)
    y el contador de medias jugadas (para la regla de las 50 jugadas).

    Atributos
    ---------
    tablero
        El ``Tablero`` con la posición actual. Es la única fuente de verdad
        sobre las piezas.
    turno
        ``Color`` que debe mover ahora.
    estado
        ``EstadoPartida``: en curso, jaque mate, ahogado, tablas o abandono.
    ganador
        ``Color`` que ganó, o ``None`` si la partida terminó en tablas.
    motivo
        Texto legible que explica por qué terminó (va al historial y a la
        pantalla). Ejemplos: "El rey negro quedó en jaque mate".
    historial
        Lista de ``Movimiento`` jugados, en orden. Sirve para mostrar la
        notación, para deshacer y para detectar repeticiones.
    promociones
        Qué se promote cada jugada del historial, indexada por su posición en
        ``historial``. Existe porque ``Movimiento`` solo sabe origen y destino:
        sin este diccionario, deshacer un peón promovido a torre devolvería una
        dama (que es el valor por defecto).
    semicontador
        Cuántos medio-movimientos van sin captura ni movimiento de peón. Es el
        campo 5 del FEN.
    numero_movimiento
        Número de jugada completa que se está jugando (1 al principio, 2 tras
        el primer movimiento negro...). Es el campo 6 del FEN.
    """

    def __init__(self, tablero: Tablero | None = None) -> None:
        # Si no se pasa tablero se usa la posición inicial estándar. Aislar
        # esto aquí permite que las pruebas construyan la partida desde un FEN
        # o desde un tablero a medida sin tocar ningún otro punto del código.
        self.tablero = tablero if tablero is not None else Tablero.posicion_inicial()
        self.turno = Color.BLANCO
        self.estado = EstadoPartida.EN_CURSO
        self.motivo = ""
        self.ganador: Color | None = None
        self.historial: list[Movimiento] = []
        self.promociones: dict[int, TipoPieza] = {}
        self.semicontador = 0
        self.numero_movimiento = 1
        # Diccionario {clave de posición: veces repetida}. Se usa para las
        # tablas por repetición. Es privado porque es un detalle interno: nadie
        # debería depender de su formato.
        self._repeticiones: dict[str, int] = {}
        self._registrar_posicion()
        # FEN de la posición **antes de la primera jugada**. Es el punto desde
        # el que ``deshacer`` reconstruye la partida. Se guarda aquí, y no se
        # deduce, porque una partida cargada desde un FEN no empieza en la
        # posición inicial estándar: si se supusiera lo contrario, deshacer
        # intentaría reproducir jugadas que no existen en ese tablero.
        self._fen_inicial = self.a_fen()

    # ------------------------------------------------------------------
    # Constructores alternativos
    # ------------------------------------------------------------------

    @classmethod
    def desde_fen(cls, fen: str) -> Partida:
        """Crea una partida a partir de una posición FEN completa.

        Se admite tanto un FEN de 6 campos (el estándar) como uno corto con
        solo la posición, porque quien pega una posición de una página web
        rara vez se molesta en escribir el resto:

            rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1

        Los campos se interpretan así:

        ==================  =================================================
        Campo               Significado
        ==================  =================================================
        1                   Placement de las piezas (lo parsea ``Tablero``).
        2                   Turno: ``w`` (blancas) o ``b`` (negras).
        3                   Derechos de enroque: ``KQkq`` o ``-``.
        4                   Casilla "al paso" o ``-``.
        5                   Medio-movimientos desde la última captura o peón.
        6                   Número de jugada completa.
        ==================  =================================================
        """
        partes = fen.strip().split(" ")
        # Quitar campos vacíos: un FEN mal pegado suele traer dobles espacios.
        partes = [parte for parte in partes if parte]
        if not partes:
            raise ErrorAjedrez("El FEN está vacío.")
        if len(partes) < 2:
            raise ErrorAjedrez("El FEN debe incluir al menos la posición y el turno.")

        # --- Campo 2: el turno ---
        letra_turno = partes[1].lower()
        if letra_turno not in ("w", "b"):
            raise ErrorAjedrez(f"Turno inválido en el FEN: {partes[1]!r}. Use 'w' o 'b'.")
        turno = Color.BLANCO if letra_turno == "w" else Color.NEGRO

        # --- Campo 3: derechos de enroque ---
        # "-" significa que no se puede enrocar por ningún lado. Cualquier
        # letra que no sea K/Q/k/q se ignora en vez de fallar: así un FEN con
        # caracteres raros no rompe la carga.
        if len(partes) > 2 and partes[2] != "-":
            derechos = {letra for letra in partes[2] if letra in "KQkq"}
        else:
            derechos = set()

        # --- Campos 1 y 4: piezas y captura al paso ---
        tablero = Tablero.desde_fen(partes[0], derechos)
        if len(partes) > 3 and partes[3] != "-":
            tablero.ultima_jugada = _jugada_al_paso(Posicion.desde_notacion(partes[3]))

        partida = cls(tablero)
        # El constructor ya registró la posición inicial con turno blanco. Como
        # ahora el turno puede ser otro, hay que *rehacer* el registro: si solo
        # se añadiera otra vez, la misma posición contaría como repetida dos
        # veces y una repetición triple se detectaría una jugada antes de tiempo.
        partida.turno = turno
        partida._reiniciar_repeticiones()

        # --- Campos 5 y 6: contadores ---
        if len(partes) > 4 and partes[4].isdigit():
            partida.semicontador = int(partes[4])
        if len(partes) > 5 and partes[5].isdigit():
            partida.numero_movimiento = int(partes[5])

        # Una posición cargada puede llegar ya terminada (por ejemplo un FEN de
        # un problema de mate). Recalcularlo evita que la aplicación acepte
        # jugadas sobre una partida que en realidad ya no admite más.
        partida.recalcular_estado()
        # El ancla para deshacer es esta misma posición, no la inicial estándar
        # (ver el comentario de ``_fen_inicial``).
        partida._fen_inicial = partida.a_fen()
        return partida

    def clonar(self) -> Partida:
        """Devuelve una copia independiente de la partida.

        Se apoya en la serialización (``to_dict``/``from_dict``) en vez de
        escribir un ``__copy__`` a mano: así la copia es *exactamente* lo que
        se guardaría en disco, y no puede desviarse de la persistencia.

        Se usa para el "deshacer": en vez de intentar retroceder al revés una jugada
        (imposible en general, por la captura al paso o la promoción), se
        vuelve a la instantánea anterior reconstruyendo el historial.
        """
        return Partida.from_dict(self.to_dict())

    # ------------------------------------------------------------------
    # Jugadas
    # ------------------------------------------------------------------

    def mover(
        self,
        origen: Posicion | str,
        destino: Posicion | str,
        promocion: TipoPieza | str | None = None,
    ) -> Movimiento:
        """Juega una jugada completa y devuelve el movimiento realizado.

        Este es **el** punto de entrada de todas las jugadas del programa
        (venga de la consola, de una IA o de una prueba). Acepta tanto objetos
        ``Posicion`` como cadenas ("e2", "e4") porque quien llama desde la
        interfaz solo tiene texto.

        El orden de las comprobaciones importa: primero que la partida siga en
        curso, después que el movimiento exista entre los legales (y no solo
        que sea "geográficamente" posible), y solo entonces se toca el tablero.

        Lanza
        -----
        PartidaTerminada
            Si la partida ya terminó.
        MovimientoIlegal
            Si la jugada no cumple las reglas (no existe, es del color
            contrario, deja al rey en jaque, promoción imposible, texto
            ilegible...).
        """
        if self.estado is not EstadoPartida.EN_CURSO:
            raise PartidaTerminada(f"La partida terminó por {self.estado.value}.")

        movimiento = Movimiento(self._a_posicion(origen), self._a_posicion(destino))

        # Se exige que el movimiento esté en la lista de legales en lugar de
        # llamar a ``Tablero.aplicar`` y dejar que él valide. La diferencia
        # importa para el jugador: la lista de legales es también la que la
        # vista usa para sugerir destinos, así que el mensaje de error y las
        # sugerencias nunca se contradicen.
        if movimiento not in self.movimientos_disponibles():
            raise MovimientoIlegal(
                f"Movimiento no permitido: {movimiento.notacion} "
                f"(turno de las {self.turno.nombre_legible.lower()})."
            )

        # La promoción se interpreta *antes* de aplicar: al llegar a la última
        # fila hay que saber a qué pieza se convierte el peón.
        tipo_promocion = self._a_tipo_promocion(promocion)

        pieza = self.tablero.obtener(movimiento.origen)
        if pieza is None:
            raise MovimientoIlegal(f"No hay pieza en {movimiento.origen.notacion}.")

        capturada = self.tablero.aplicar(movimiento, tipo_promocion)

        # Los derechos de enroque no los puede quitar el tablero (no sabe de
        # reglas de partida), así que los gestiona esta clase.
        self._registrar_derechos_enroque(movimiento, pieza, capturada)

        self.historial.append(movimiento)
        # Si hubo promoción se apunta en qué jugada del historial ocurrió. Sin
        # este apunte, deshacer la volvería a hacer como dama.
        if tipo_promocion is not None and pieza.tipo is TipoPieza.PEON:
            self.promociones[len(self.historial) - 1] = tipo_promocion

        # Regla de las 50 jugadas: el contador se reinicia con cualquier
        # captura o movimiento de peón, y sube en cualquier otra jugada.
        if capturada is not None or pieza.tipo is TipoPieza.PEON:
            self.semicontador = 0
        else:
            self.semicontador += 1

        # El número de jugada avanza cuando el negro acaba de mover, porque la
        # "jugada N" son los dos medio-movimientos: blancas y negras.
        if pieza.color is Color.NEGRO:
            self.numero_movimiento += 1

        self.turno = self.turno.contrario
        self._registrar_posicion()
        self.recalcular_estado()
        return movimiento

    def movimientos_disponibles(self) -> list[Movimiento]:
        """Movimientos legales del color que tiene el turno."""
        return self.tablero.movimientos_legales(self.turno)

    def esta_en_jaque(self, color: Color | None = None) -> bool:
        """Indica si el rey indicado (por defecto, el del turno) está amenazado."""
        return self.tablero.esta_en_jaque(color if color is not None else self.turno)

    def jugadas_en_notacion(self) -> list[str]:
        """El historial escrito en notación legible, para mostrarlo en pantalla.

        Se numeran las jugadas completas (1. e4 e5  2. Nf3 Nc6...), que es como
        se lee una partida de verdad, en vez de una lista suelta de casillas.
        """
        lineas = []
        for indice in range(0, len(self.historial) - 1, 2):
            blancas = self.historial[indice]
            negras = self.historial[indice + 1] if indice + 1 < len(self.historial) else None
            numero = indice // 2 + 1
            texto = f"{numero}. {blancas.notacion}"
            if negras is not None:
                texto += f" {negras.notacion}"
            lineas.append(texto)
        # Si el último movimiento fue de las blancas, su jugada queda sin
        # respuesta y se añade su línea sola para no perderla de la vista.
        if len(self.historial) % 2 == 1:
            lineas.append(f"{len(self.historial) // 2 + 1}. {self.historial[-1].notacion}")
        return lineas

    def deshacer(self) -> Movimiento | None:
        """Deshace la última jugada y devuelve el movimiento deshecho.

        Se implementa *reconstruyendo* la partida desde el ancla
        (``_fen_inicial``) y el historial, no calculando la jugada inversa. Es
        la decisión correcta: la inversa de "Ne5xd4" o de una promoción no es
        trivial, y un error ahí corrompería la partida; volver a aplicar el
        historial es prácticamente imposible de equivocar.

        Tres detalles que hacen que funcione de verdad:

        * Se reconstruye **desde el ancla y no desde la posición inicial
          estándar**, para que también funcione en una partida cargada desde un
          FEN a media partida.
        * Se repropone la promoción de cada jugada con ``promociones``, para no
          perder las UNDER-promociones (torre, alfil o caballo).
        * Se reconstruye sobre una partida aparte y solo al final se copian sus
          atributos sobre *esta* instancia, de forma que el controlador, la vista
          y quien guardó una referencia sigan apuntando al mismo objeto. Si
          algo fallara a media reconstrucción, esta partida quedaría intacta.

        Devuelve ``None`` si no hay nada que deshacer. También devuelve
        ``None`` si la partida terminó por abandono: la última acción fue el
        abandono, no una jugada, así que no hay jugada que deshacer.
        """
        if not self.historial or self.estado is EstadoPartida.ABANDONO:
            return None
        ultima = self.historial[-1]

        restaurada = Partida.desde_fen(self._fen_inicial)
        for indice, movimiento in enumerate(self.historial[:-1]):
            restaurada.mover(movimiento.origen, movimiento.destino, self.promociones.get(indice))

        # Se copian los atributos sobre *esta* instancia (y no se devuelve la
        # nueva) para que el controlador, la vista y quien guardó una
        # referencia a esta partida sigan apuntando al mismo objeto.
        self.__dict__.update(restaurada.__dict__)
        return ultima

    def abandonar(self) -> None:
        """El jugador del turno abandona: gana el contrario."""
        if self.estado is not EstadoPartida.EN_CURSO:
            raise PartidaTerminada("La partida ya terminó.")
        self.estado = EstadoPartida.ABANDONO
        self.motivo = f"Las {self.turno.nombre_legible.lower()} abandonaron"
        self.ganador = self.turno.contrario

    def reiniciar(self) -> None:
        """Empieza una partida nueva desde la posición inicial.

        Se reinicia llamando al propio ``__init__``: es la forma de garantizar
        que la partida nueva tiene *exactamente* el mismo estado que una recién
        creada, sin tener que acordarse de poner a cero cada atributo.

        **Siempre empiezan las blancas.** No es un parámetro a propósito: en
        ajedrez es una regla, no una preferencia de quien abre el programa. El
        bando con el que juega la persona es cosa de la aplicación (el
        controlador lo sabe), y elijiendo negras no se puede mover nada hasta
        que mueva el otro bando, que es exactamente como funciona el ajedrez.
        Para practicar los dos bandos en la misma partida está el modo "los dos
        colores", que es lo que no impone ningún bando.

        Una posición con el turno de las negras sí se puede *cargar* (un FEN con
        ``b``), pero eso es una posición que viene de fuera, no una partida que
        empieza aquí.
        """
        self.__init__()


    def esta_terminada(self) -> bool:
        """True si la partida ya no admite más jugadas."""
        return self.estado is not EstadoPartida.EN_CURSO

    def resumen(self) -> str:
        """Texto breve con el estado actual, listo para imprimir.

        Ejemplos: ``"Turno de las negras (jaque)"`` o
        ``"Jaque mate: blanco. El rey negro quedó en jaque mate"``.
        """
        if self.estado is EstadoPartida.EN_CURSO:
            turno = "Turno de las blancas" if self.turno is Color.BLANCO else "Turno de las negras"
            jaque = " (jaque)" if self.esta_en_jaque() else ""
            return f"{turno}{jaque}"
        ganador = (
            self.ganador.nombre_legible.lower() if self.ganador is not None else "sin ganador"
        )
        return f"{self.estado.value.capitalize()}: {ganador}. {self.motivo}"

    # ------------------------------------------------------------------
    # FEN: lectura y escritura de la posición
    # ------------------------------------------------------------------

    def a_fen(self) -> str:
        """Representación FEN completa de la posición actual.

        Es lo que se guarda en el almacenamiento ``FENStorage`` y lo que se
        puede pegar en cualquier programa de ajedrez para seguir la partida.

        Se construyen las filas de la 8 a la 1 (en eso va al revés el FEN) y
        las casillas vacías consecutivas se agrupan en un dígito: "3" significa
        "tres casillas vacías". Sin ese agrupamiento, una fila vacía sería
        "11111111" en lugar de "8".
        """
        filas = []
        for fila in range(7, -1, -1):
            texto = ""
            vacias = 0
            for columna in range(8):
                pieza = self.tablero.obtener(Posicion(columna, fila))
                if pieza is None:
                    # Se cuentan las vacías y se aplazan: solo se escribe el
                    # número cuando aparece la siguiente pieza (o al final).
                    vacias += 1
                    continue
                if vacias:
                    texto += str(vacias)
                    vacias = 0
                texto += pieza.letra_fen
            if vacias:
                texto += str(vacias)
            filas.append(texto)

        # Los derechos de enroque se escriben en el orden canónico KQkq, no en
        # el que devuelva `sorted`, para que el mismo tablero produzca siempre
        # el mismo FEN (si no, dos FEN equivalentes parecerían distintos).
        enroque = ""
        for letra in "KQkq":
            if letra in self.tablero.derechos_enroque:
                enroque += letra
        if not enroque:
            enroque = "-"

        return (
            f"{'/'.join(filas)} {self.turno.letra_fen} {enroque} "
            f"{self.casilla_al_paso()} {self.semicontador} {self.numero_movimiento}"
        )

    def casilla_al_paso(self) -> str:
        """Casilla objetivo de una posible captura al paso, o ``"-"``.

        Solo se escribe si la última jugada fue un avance de peón de dos
        casillas: en cualquier otro caso no hay nada que capturar al paso y el
        FEN lleva ``-``.

        El avance en L de un caballo también salta dos filas, así que mirar solo
        las filas no basta (un caballo de g1 a f3 produciría la absurda casilla
        "g2" y el FEN no se podría volver a leer). Por eso se comprueba además
        que en la casilla de destino haya un peón: tras el avance doble es el
        propio peón que se ha movido, y si la última jugada fue una captura
        al paso la casilla de destino está vacía y también se descarta.
        """
        ultima = self.tablero.ultima_jugada
        if ultima is None or abs(ultima.destino.fila - ultima.origen.fila) != 2:
            return "-"
        if ultima.origen.columna != ultima.destino.columna:
            return "-"
        movido = self.tablero.obtener(ultima.destino)
        if movido is None or movido.tipo is not TipoPieza.PEON:
            return "-"
        # La casilla "al paso" es la que queda a mitad de camino.
        fila = (ultima.origen.fila + ultima.destino.fila) // 2
        return Posicion(ultima.origen.columna, fila).notacion

    # ------------------------------------------------------------------
    # Estado y reglas de fin de partida
    # ------------------------------------------------------------------

    def recalcular_estado(self) -> None:
        """Recalcula el estado de la partida a partir de la posición actual.

        Se llama después de cada jugada y también al cargar una partida. El
        orden de las comprobaciones es intencionado y va de "más grave" a
        "menos grave": primero el mate y el ahogado (que son finales reales y
        no admiten continuación), y después las tres formas de tablas.

        Importante: si la partida ya terminó (por abandono, por ejemplo) este
        método **no** la reabre. Solo se evalúa el final si la partida
        esté en curso.
        """
        if self.estado is not EstadoPartida.EN_CURSO:
            return

        if not self.movimientos_disponibles():
            # Sin ningún movimiento legal solo hay dos posibilidades, y se
            # distinguen por si el rey está amenazado: con jaque es mate, sin
            # jaque es ahogado (tablas). La propiedad clave de la partida es
            # que en ambos casos el que tiene el turno es el que pierde o
            # empata, así que el ganador es el contrario.
            if self.esta_en_jaque():
                self.estado = EstadoPartida.JAQUE_MATE
                self.ganador = self.turno.contrario
                self.motivo = f"El rey {self.turno.nombre_legible.lower()} quedó en jaque mate"
            else:
                self.estado = EstadoPartida.AHOGADO
                self.motivo = f"El rey {self.turno.nombre_legible.lower()} quedó ahogado"
            return

        if self.semicontador >= MEDIO_MOVIMIENTOS_PARA_TABLAS:
            self._declarar_tablas(
                "Se cumplieron las 50 jugadas sin capturas ni movimientos de peón."
            )
            return

        if self._material_insuficiente():
            self._declarar_tablas("No queda material suficiente para dar mate.")
            return

        if max(self._repeticiones.values(), default=0) >= REPETICIONES_PARA_TABLAS:
            self._declarar_tablas("La posición se repitió tres veces.")

    def _declarar_tablas(self, motivo: str) -> None:
        """Marca la partida como empatada, dejando constancia del motivo.

        ``ganador`` se deja a ``None``: en tablas no gana nadie. Es importante
        no dejar el valor anterior, porque la vista lo usa para decir quién
        ganó y un empate no debe adjudicarse al último que movió.
        """
        self.estado = EstadoPartida.TABLAS
        self.ganador = None
        self.motivo = motivo

    def _material_insuficiente(self) -> bool:
        """True si no queda material en el tablero para forzar un mate.

        Se detectan los tres casos en que es matemáticamente imposible dar
        mate, que son los que hacen tablas automáticamente en un torneo:

        1. Solo quedan reyes.
        2. Queda un único alfil (o un único caballo): no puede dar mate solo.
        3. Solo quedan alfiles y todos están en casillas del mismo color: dos
           alfiles en el mismo color no pueden llegar nunca a una posición de
           mate.
        """
        piezas = [pieza for pieza in self.tablero.piezas() if pieza.tipo is not TipoPieza.REY]
        # Caso 1: solo reyes.
        if not piezas:
            return True
        # Caso 3: solo alfiles, todos en el mismo color de casilla. El color de
        # una casilla es la paridad de columna+fila, así que basta con mirar
        # si todos dan el mismo resto al dividir entre 2.
        if all(pieza.tipo is TipoPieza.ALFIL for pieza in piezas):
            colores = {(pieza.posicion.columna + pieza.posicion.fila) % 2 for pieza in piezas}
            return len(colores) == 1
        # Caso 2: una sola pieza, y no es un rey.
        if len(piezas) == 1 and piezas[0].tipo in (TipoPieza.ALFIL, TipoPieza.CABALLO):
            return True
        return False

    def _registrar_posicion(self) -> None:
        """Anota la posición actual para poder detectar repeticiones.

        Lo que se compara no es el tablero a secas, sino la **situación** de
        juego, que es lo que dice el reglamento al hablar de repetición. La
        clave lleva cuatro cosas:

        1. Las piezas y sus casillas (``Tablero.clave()``).
        2. El color que tiene el turno. No es repetición la misma distribución
           con distinto color en turno, porque las opciones legales son
           distintas.
        3. Los **derechos de enroque**. Con las mismas piezas pero sin derecho
           a enrocar la posición es peor para quien tiene el turno, y el
           reglamento la considera otra posición.
        4. La casilla "al paso", pero **solo si de verdad se puede capturar**.
           Hay posiciones con el mismo tablero donde un peón acaba de avanzar
           dos casillas y el otro bando no tiene ningún peón al lado: ahí la
           captura al paso no existe y la posición es la misma. Se comprueba
           mirando los movimientos legales, que es la forma exacta (y no una
           aproximación) de saber si la captura está disponible.
        """
        clave = self._clave_de_repeticion()
        self._repeticiones[clave] = self._repeticiones.get(clave, 0) + 1

    def _clave_de_repeticion(self) -> str:
        """Clave que identifica una posición a efectos de repetición."""
        casilla_al_paso = self.casilla_al_paso()
        if casilla_al_paso != "-":
            # Solo cuenta si hay una jugada legal que termine en esa casilla,
            # que es justamente lo que hace el peón al capturar al paso.
            if not any(
                movimiento.destino.notacion == casilla_al_paso
                for movimiento in self.movimientos_disponibles()
            ):
                casilla_al_paso = "-"
        derechos = "".join(letra for letra in "KQkq" if letra in self.tablero.derechos_enroque)
        return f"{self.tablero.clave()}{self.turno.letra_fen}{derechos or '-'}{casilla_al_paso}"

    def _reiniciar_repeticiones(self) -> None:
        """Vacía el registro de repeticiones y anota solo la posición actual.

        Se necesita al cargar una partida: si no, la posición inicial se
        contaría junto con la posición del FEN y el contador quedaría
        desfasado.
        """
        self._repeticiones = {}
        self._registrar_posicion()

    def _registrar_derechos_enroque(
        self,
        movimiento: Movimiento,
        pieza: Pieza,
        capturada: Pieza | None,
    ) -> None:
        """Quita los derechos de enroque que la jugada acabada de invalidar.

        Los derechos se pierden en dos situaciones, y esta es toda la
        lógica:

        * la pieza **sale** de su casilla inicial (rey o torre). Da igual a
          dónde vaya después: en cuanto se mueve, ese enroque ya no es
          legal para siempre.
        * la jugada **captura** en una casilla inicial una torre o un rey.

        La tabla se escribe una vez con los seis pares (casilla, tipo) -> letras
        de derechos que se pierden, y se recorre dos veces: la primera para
        tratar la salida de la pieza, la segunda para tratar la captura. Se
        podría hacer en un solo bucle, pero it'd have que comprobar "o sale de
        aquí, o aterriza aquí" pieza a pieza; dos bucles lo dicen literalmente.
        """
        origenes = {
            (Posicion(4, 0), TipoPieza.REY): {"K", "Q"},
            (Posicion(7, 0), TipoPieza.TORRE): {"K"},
            (Posicion(0, 0), TipoPieza.TORRE): {"Q"},
            (Posicion(4, 7), TipoPieza.REY): {"k", "q"},
            (Posicion(7, 7), TipoPieza.TORRE): {"k"},
            (Posicion(0, 7), TipoPieza.TORRE): {"q"},
        }
        # 1) La pieza sale de su casilla inicial.
        for (posicion, tipo), derechos in origenes.items():
            if movimiento.origen == posicion and pieza.tipo is tipo:
                self.tablero.derechos_enroque -= derechos
        # 2) La jugada captura una pieza que estaba en su casilla inicial.
        for (posicion, tipo), derechos in origenes.items():
            if movimiento.destino == posicion and capturada is not None and capturada.tipo is tipo:
                self.tablero.derechos_enroque -= derechos

    # ------------------------------------------------------------------
    # Conversión de Entrada/Salida (texto del usuario y objetos del dominio)
    # ------------------------------------------------------------------

    def _a_posicion(self, valor: Posicion | str) -> Posicion:
        """Convierte lo que el jugador escribió en una ``Posicion``.

        Acepta las dos formas porque el mismo método se usa desde la
        interfaz (texto) y desde las pruebas y la IA (objetos ya válidos).
        """
        if isinstance(valor, Posicion):
            return valor
        return Posicion.desde_notacion(valor)

    def _a_tipo_promocion(self, valor: TipoPieza | str | None) -> TipoPieza | None:
        """Convierte lo que el jugador escribió en un ``TipoPieza`` de promoción.

        Se aceptan muchas formas porque son todas las que la gente usa de
        verdad: el nombre ("dama"), la letra de FEN ("q") o la inicial en
        español ("d"). ``None`` significa "sin promoción": es válido, y en ese
        caso ``Tablero`` promueve a dama (la regla por defecto).
        """
        if valor is None:
            return None
        if isinstance(valor, TipoPieza):
            return valor
        if isinstance(valor, str):
            texto = valor.strip().lower()
            tipo = LETRAS_PROMOCION.get(texto)
            if tipo is None:
                # Segundo intento: el nombre canónico del enum ("peon",
                # "rey"...). Sirve para detectar el error más común, que es
                # Se intenta promover a rey o a peón.
                try:
                    tipo = TipoPieza(texto)
                except ValueError as error:
                    raise MovimientoIlegal(
                        f"Promoción desconocida: {valor!r}. Use dama, torre, alfil o caballo."
                    ) from error
            if tipo not in TIPOS_PROMOCION:
                raise MovimientoIlegal("Un peón solo puede promover a dama, torre, alfil o caballo.")
            return tipo
        raise MovimientoIlegal("La promoción debe ser un TipoPieza o su nombre.")

    # ------------------------------------------------------------------
    # Persistencia: conversión a y desde diccionario
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serializa la partida completa a un diccionario (sin metadatos).

        La usan dos cosas distintas y por eso está separada de los metadatos
        del almacenamiento:

        * el ``JSONStorage``, que envuelve este diccionario con un id, un
          nombre y una fecha,
        * ``clonar()``, que reconstruye la partida a partir de aquí.

        Dos detalles de diseño:

        1. El tablero se serializa entero, con su campo ``ultima_jugada``, en
           lugar de reconstruirse reproduciendo el historial. Así el estado
           cargado es *exactamente* el que se guardó, sin depender de que
           ``mover()`` siga siendo determinista.
        2. Las promociones van en un diccionario aparte
           (``{"2": "torre"}``: jugada del historial -> tipo). El historial en
           sí queda como una lista de movimientos puros, porque es lo que
           entiende ``Movimiento.from_dict`` y lo que cuenta la vista para
           numerar. Sin ese diccionario, recargar y deshacer convertiría una
           torre en una dama.
        3. Se guarda también ``fen_inicial``, el ancla desde la que se
           reconstruye la partida al deshacer. Un archivo guardado por una
           versión anterior no la tendrá, y entonces se usa la posición
           inicial estándar (que es lo único que se puede suponer).
        """
        return {
            "tablero": self.tablero.to_dict(),
            "turno": self.turno.value,
            "estado": self.estado.value,
            "ganador": self.ganador.value if self.ganador is not None else None,
            "motivo": self.motivo,
            "historial": [movimiento.to_dict() for movimiento in self.historial],
            "promociones": {
                str(indice): tipo.value for indice, tipo in self.promociones.items()
            },
            "semicontador": self.semicontador,
            "numero_movimiento": self.numero_movimiento,
            "fen_inicial": self._fen_inicial,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Partida:
        """Reconstruye una partida serializada con ``to_dict``.

        Los valores se revalidan con los ``Enum``: si alguien edita el JSON a
        mano y escribe ``"turno": "azul"``, el error salta aquí, al cargar, y
        no dos horas después en una jugada.
        """
        partida = cls(Tablero.from_dict(data["tablero"]))
        partida.turno = Color(data["turno"])
        partida.estado = EstadoPartida(data["estado"])
        ganador = data.get("ganador")
        partida.ganador = Color(ganador) if ganador else None
        partida.motivo = data.get("motivo", "")
        partida.historial = [Movimiento.from_dict(item) for item in data.get("historial", [])]
        # Las claves del JSON son texto, así que el índice de la jugada (un
        # número) vuelve como cadena y se convierte aquí.
        partida.promociones = {
            int(indice): TipoPieza(tipo) for indice, tipo in data.get("promociones", {}).items()
        }
        partida.semicontador = int(data.get("semicontador", 0))
        partida.numero_movimiento = int(data.get("numero_movimiento", 1))
        partida._fen_inicial = data.get("fen_inicial") or FEN_INICIAL
        # Las repeticiones no se serializan (son un caché, no un dato de la
        # partida): se recomputan al terminar de cargar. Como no se puede
        # recuperar el historial de repeticiones de las posiciones pasadas
        # (no se guardan), la repetición triple solo se detectará a partir de
        # ahora. Es una limitación consciente: el FEN y el JSON guardan la
        # *posición*, no la lista de posiciones visitadas.
        partida._reiniciar_repeticiones()
        return partida

    def __str__(self) -> str:
        return f"{self.tablero}\n{self.resumen()}"
