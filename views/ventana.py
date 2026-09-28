"""Ventana jugable: un tablero de verdad, con botones y sin diálogos de menú.

Esta es **la única** pantalla del programa, y **no** es una implementación de
``views.interfaz.InterfazVista``. Es importante decir por qué, porque es la
decisión de diseño que hace que esto funcione sin reescribir el controlador.

Las dos vistas que hubo antes (la consola y la ventana de menús) eran
*consumidoras* de un controlador que escribe en bloque: el controlador llamaba a
``menu_partida()`` y se quedaba parado hasta que alguien contestaba. Para hablar
con una de ellas, la ventana tenía que saber **preguntar**, y preguntar en
``tkinter`` significa abrir un diálogo modal y esperar con ``wait_window()``. Por
esos dos motivos tenían menús y no botones: no es que no se pudiera, es que un
diálogo modal es justamente lo que hace posible reutilizar el controlador tal
cual. Ambas se han borrado, y el esquema de "el controlador pregunta y espera" se
queda sin uso junto con ellas.

Una ventana de ajedrez de verdad no tiene menús: tiene un tablero, se hace clic
en dos casillas y la jugada está hecha. No hay nada que preguntar. Y si no hay
nada que preguntar, no hace falta ni puente de hilos: nadie espera, así que no
hay nada que repartir entre el hilo que dibuja y el que decide.

Por eso aquí la relación es **invertida**. No es el controlador el que empuja
menús hacia la pantalla, es la pantalla la que **tira** de las acciones del
controlador cuando alguien pulsa un botón o hace clic en una casilla:

    clic en e2, clic en e4   ->  controlador.aplicar_jugada("e2e4")
    botón Deshacer           ->  controlador.deshacer()
    botón Guardar            ->  controlador.guardar("nombre")
    botón Cargar             ->  controlador.cargar(clave)

Esos métodos ya existían y ya estaban probados, porque son las acciones que el
menú de la consola llamaba por dentro. Lo único que faltaba era una puerta de
entrada para las jugadas, y esa es ``PartidaController.aplicar_jugada``: la misma
validación, la misma traducción de errores y la misma comprobación de turno que
usaba la consola, pero sin la pregunta previa. Por eso esta ventana puede
aprovechar el controlador entero sin copiar ni una línea de su lógica.

Y ``InterfazVista`` se conserva, aunque ya no lo implemente ninguna pantalla,
porque el bucle de menús del controlador sigue escrito y probado contra él (ver
``views/__init__.py`` y la nota del README sobre qué queda sin uso). Esta
ventana no lo cumple **a propósito**: no es intercambiable con una vista de
menús, porque no tiene menús. Decir que cumple el contrato sería mentir, y un
``Protocol`` que miente es peor que no tener contrato.

Lo que sí comparte con el resto del programa, y es lo que importa: ``models/``
no sabe que esto existe, ``storage/`` tampoco, y el controlador no ha tenido que
cambiar de forma para acomodar la pantalla. La diferencia entre una ventana con
menús y una con botones está entera en la vista, que es donde debería estar.

Para arrancarla, ``python main_ventana.py`` en la raíz del proyecto.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterator
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from controllers.partida_controller import PartidaController
from models.enums import Color, TipoPieza
from models.partida import Partida
from models.pieza import SIMBOLOS, TIPOS_PROMOCION
from models.posicion import Movimiento, Posicion
from storage.base_storage import BaseStorage
from views.interfaz import texto_del_error

# Lado de cada casilla, en píxeles. Son deliberadamente grandes porque aquí las
# casillas se pulsan con el ratón y tienen que ser cómodas de acertar.
LADO_CASILLA = 56
MARGEN = 24

CLARA = "#ecd9bd"
OSCURA = "#a9784f"
FONDO = "#313131"
TEXTO = "#f2f2f2"
SELECCION = "#f7ec74"
ULTIMA = "#b7d47a"
JAQUE = "#e05c5c"
DESTINO_ACTIVO = "#f0d264"
DESTINO_INACTIVO = "#8a8a8a"

# Letra de promoción de cada pieza. Es el inverso de
# ``models.pieza.LETRAS_PROMOCION`` (que va de texto a tipo): aquí hace falta al
# revés, porque quien elige promoción tiene un ``TipoPieza`` y necesita escribir
# la jugada que el controlador va a leer.
LETRA_DE_PROMOCION = {
    TipoPieza.DAMA: "q",
    TipoPieza.TORRE: "r",
    TipoPieza.ALFIL: "b",
    TipoPieza.CABALLO: "n",
}


class SalidaDeConsola:
    """Lo mínimo que el controlador necesita para poder hablar con la ventana.

    El controlador fue escrito contando con que su vista sabe *preguntar*, y por
    eso llama a ``self.vista.mostrar_mensaje(...)`` por todas partes. Esta clase
    le da justo eso, y nada más: no implementa ``InterfazVista`` (no tiene
    ``menu_partida`` ni ``pedir_jugada``, y no los va a tener nunca, porque aquí no
    hay menús) pero sí los cuatro métodos que el controlador invoca de verdad en
    el camino que usa esta ventana.

    ``pedir_confirmacion`` sí es una pregunta de verdad, y se resuelve con un
    ``askyesno``. No es una contradicción: pregunta es "sí o no" y se contesta en
    un segundo, no "elige una de estas ocho opciones y el juego se queda parado".
    El tipo de pregunta que hay que quitar de aquí es el menú, no la confirmación.

    ``elegir_color`` no pregunta nada: devuelve el color que ya esté marcado en
    el panel lateral. También es deliberado. En la consola el color se pregunta
    porque es una decisión que se toma una vez al empezar; en una ventana hay un
    selector siempre visible, y volver a preguntar sería abrir un diálogo para
    preguntar algo que ya se está viendo en pantalla.
    """

    def __init__(self, ventana: "VentanaAjedrez") -> None:
        self.ventana = ventana

    def mostrar_mensaje(self, mensaje: str) -> None:
        self.ventana._anotar(mensaje)

    def mostrar_error(self, error: Exception | str) -> None:
        self.ventana._anotar(texto_del_error(error), error=True)

    def escribir(self, texto: str = "") -> None:
        if texto:
            self.ventana._anotar(texto)

    def titulo(self, texto: str) -> None:
        self.ventana._anotar(texto)

    def pedir_confirmacion(self, pregunta: str) -> bool:
        return bool(messagebox.askyesno("Confirmar", pregunta, parent=self.ventana.root))

    def elegir_color(self) -> Color | None:
        return self.ventana.color


class VentanaAjedrez:
    """El tablero, el panel lateral y los botones.

    No hereda de nada y no implementa ningún ``Protocol``: es una pantalla que
    manda, no una pantalla a la que se le pregunte. Lo que tiene es un
    ``PartidaController`` al que llama, y un ``BaseStorage`` para el guardado.
    """

    def __init__(
        self,
        root: tk.Tk,
        storage: BaseStorage | None = None,
        controlador: PartidaController | None = None,
    ) -> None:
        self.root = root
        self.storage = storage
        if controlador is None:
            self.controlador = PartidaController(vista=SalidaDeConsola(self), storage=storage)
        else:
            controlador.vista = SalidaDeConsola(self)
            self.controlador = controlador

        # Casilla seleccionada y a dónde puede ir desde ella. Se guardan aquí
        # porque son el estado de la *interacción*, no el de la partida: no van
        # al historial, no se guardan y no se deshacen.
        self.origen: Posicion | None = None
        self.destinos: list[Movimiento] = []
        # Color con el que se juega. ``None`` significa "los dos", que es lo que
        # permite practicar con los dos bandos en la misma partida.
        self.color: Color | None = Color.BLANCO
        self.girada = False
        # El bando y el turno de la partida se ponen de acuerdo pasando por el
        # controlador, no asignando las dos cosas por separado: es el quien sabe
        # que si el bando es negro el turno inicial tiene que ser el negro. Con
        # blanco (el valor de arriba) esto no cambia nada, pero deja el invariante
        # en un solo sitio desde el primer momento.
        self.controlador.nueva_partida(self.color)

        self._construir()
        self._refrescar()

    # ------------------------------------------------------------------
    # Estructura
    # ------------------------------------------------------------------

    def _construir(self) -> None:
        self.root.title("Ajedrez")
        self.root.configure(background=FONDO)

        contenedor = ttk.Frame(self.root, padding=10)
        contenedor.grid(row=0, column=0, sticky="nsew")

        # -- tablero --
        self.lienzo = tk.Canvas(
            contenedor,
            width=LADO_CASILLA * 8 + MARGEN * 2,
            height=LADO_CASILLA * 8 + MARGEN * 2,
            background=FONDO,
            highlightthickness=0,
        )
        self.lienzo.grid(row=0, column=0, sticky="nsew")
        self.lienzo.bind("<Button-1>", self._al_hacer_clic)
        self.lienzo.bind("<Motion>", self._al_mover_el_raton)

        # -- panel lateral --
        panel = ttk.Frame(contenedor, padding=(14, 0, 0, 0))
        panel.grid(row=0, column=1, sticky="ns")

        ttk.Label(panel, text="Juegas con:", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.opciones_color = tk.StringVar(panel, value="blancas")
        marco_color = ttk.Frame(panel)
        marco_color.grid(row=1, column=0, sticky="w", pady=(2, 12))
        for columna, (valor, texto) in enumerate(
            (("blancas", "Blancas"), ("negras", "Negras"), ("ambas", "Los dos colores"))
        ):
            ttk.Radiobutton(
                marco_color, text=texto, value=valor,
                variable=self.opciones_color, command=self._al_cambiar_color,
            ).grid(row=0, column=columna, padx=(0, 10))

        self.etiqueta_estado = ttk.Label(panel, text="", font=("Segoe UI", 12, "bold"))
        self.etiqueta_estado.grid(row=2, column=0, sticky="w")

        self.etiqueta_turno = ttk.Label(panel, text="", font=("Segoe UI", 10))
        self.etiqueta_turno.grid(row=3, column=0, sticky="w", pady=(2, 12))

        # -- historial --
        ttk.Label(panel, text="Jugadas", font=("Segoe UI", 9, "bold")).grid(
            row=4, column=0, sticky="w"
        )
        marco_historial = ttk.Frame(panel)
        marco_historial.grid(row=5, column=0, sticky="nsew")
        self.historial = tk.Text(
            marco_historial, width=32, height=15, wrap="word", font=("Consolas", 10)
        )
        barra = ttk.Scrollbar(marco_historial, orient="vertical", command=self.historial.yview)
        self.historial.configure(yscrollcommand=barra.set, state="disabled")
        self.historial.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")

        # -- FEN --
        ttk.Label(panel, text="FEN", font=("Segoe UI", 9, "bold")).grid(
            row=6, column=0, sticky="w", pady=(12, 0)
        )
        self.campo_fen = ttk.Entry(panel, font=("Consolas", 9))
        self.campo_fen.grid(row=7, column=0, sticky="ew", pady=(2, 4))
        ttk.Button(panel, text="Copiar FEN", command=self._copiar_fen).grid(
            row=8, column=0, sticky="ew"
        )

        # -- botones --
        self.botones: dict[str, ttk.Button] = {}
        acciones = (
            ("nueva", "Partida nueva", self._nueva_partida),
            ("girar", "Girar tablero", self._girar),
            ("deshacer", "Deshacer", self._deshacer),
            ("guardar", "Guardar", self._guardar),
            ("cargar", "Cargar", self._cargar),
            ("listar", "Ver guardadas", self._listar),
            ("borrar", "Borrar", self._borrar),
            ("tablas", "Declarar tablas", self._tablas),
            ("abandonar", "Abandonar", self._abandonar),
        )
        for indice, (clave, texto, accion) in enumerate(acciones):
            fila, columna = divmod(indice, 2)
            boton = ttk.Button(panel, text=texto, command=accion)
            boton.grid(row=9 + fila, column=columna, sticky="ew", padx=(0, 5), pady=2)
            self.botones[clave] = boton
        filas_botones = 9 + (len(acciones) + 1) // 2

        # -- avisos --
        ttk.Label(panel, text="Avisos", font=("Segoe UI", 9, "bold")).grid(
            row=filas_botones, column=0, sticky="w", pady=(12, 0)
        )
        self.avisos = tk.Text(panel, width=32, height=6, wrap="word", font=("Segoe UI", 9))
        self.avisos.grid(row=filas_botones + 1, column=0, sticky="ew")
        self.avisos.tag_configure("error", foreground="#ff8080")

        panel.columnconfigure(0, weight=1)
        self.root.minsize(720, 580)

    # ------------------------------------------------------------------
    # Dibujo del tablero
    # ------------------------------------------------------------------

    def _a_pantalla(self, posicion: Posicion) -> tuple[int, int]:
        """Columna y fila de pantalla de una casilla del modelo, dentro del lienzo.

        El modelo tiene la fila 0 abajo (es la del rey blanco) y la pantalla la
        tiene arriba, así que sin ``girada`` se invierte la fila. Con ``girada``
        se invierten las dos, que es lo que hace un tablero que se da la vuelta:
        un 180º, no un espejo.

        Este es el **único** sitio donde se decide dónde cae cada casilla. El
        dibujo, el clic y el ratón pasan por aquí (directamente o con
        ``_casillas``), de modo que no puede pasar que lo que se ve y lo que se
        clican sean casillas distintas.
        """
        if self.girada:
            return 7 - posicion.columna, posicion.fila
        return posicion.columna, 7 - posicion.fila

    def _de_pantalla(self, x: int, y: int) -> Posicion | None:
        """La casilla del modelo que hay bajo un punto del lienzo, o ``None``.

        Es la inversa exacta de ``_a_pantalla``: aplicarla y deshacerla tiene que
        devolver la casilla de partida. Sin girada se invierte la fila; girada se
        invierten las dos, como en el giro de 180º.
        """
        columna = int((x - MARGEN) // LADO_CASILLA)
        fila = int((y - MARGEN) // LADO_CASILLA)
        if not (0 <= columna < 8 and 0 <= fila < 8):
            return None
        if self.girada:
            return Posicion(7 - columna, fila)
        return Posicion(columna, 7 - fila)

    def _casillas(self) -> Iterator[tuple[Posicion, int, int]]:
        """Las 64 casillas del modelo con su sitio en la pantalla.

        Se recorren una sola vez y se usan para pintar, para el clic y para el
        ratón. Tener el recorrido en un único sitio es lo que evita que el
        dibujo y el clic se desincronicen: si cada uno calculara su propia
        cuenta, bastaría con invertir una fila en uno de los dos para que
        clicasen casillas distintas de las que se ven (que es exactamente el
        bug que había).
        """
        for columna in range(8):
            for fila in range(8):
                posicion = Posicion(columna, fila)
                x_col, y_fila = self._a_pantalla(posicion)
                yield posicion, x_col, y_fila

    def _pintar_tablero(self) -> None:
        # ``delete("all")`` y no ``delete("todo")``: en un canvas de Tk, todos los
        # elementos pertenecen a la etiqueta "all", y "todo" no es una etiqueta
        # que exista, así que ``delete("todo")`` no borra nada. El tablero se
        # dibujaría encima del anterior una y otra vez, sin limpiar.
        self.lienzo.delete("all")
        partida = self.controlador.partida
        tablero = partida.tablero
        fuente = self._fuente_de_piezas()

        # El rey en jaque se resalta, y para saber cuál hay que mirar el turno:
        # el jaque siempre es del rey que no está moviendo.
        rey_en_jaque = None
        if partida.esta_en_jaque():
            rey = tablero.rey_de(partida.turno)
            rey_en_jaque = rey.posicion if rey is not None else None

        ultima = tablero.ultima_jugada
        casillas_ultima = {ultima.origen, ultima.destino} if ultima is not None else set()
        destinos = {movimiento.destino for movimiento in self.destinos}

        # Cuando no es tu turno el tablero se atenúa. Con ``color`` a ``None``
        # (los dos colores) el turno es siempre tuyo, así que nunca se atenúa.
        activo = not partida.esta_terminada() and (self.color is None or partida.turno is self.color)

        for posicion, x_col, y_fila in self._casillas():
            x0 = MARGEN + x_col * LADO_CASILLA
            y0 = MARGEN + y_fila * LADO_CASILLA
            centro_x = x0 + LADO_CASILLA / 2
            centro_y = y0 + LADO_CASILLA / 2

            self.lienzo.create_rectangle(
                x0, y0, x0 + LADO_CASILLA, y0 + LADO_CASILLA,
                fill=OSCURA if posicion.es_oscura else CLARA, outline="",
            )
            self._pintar_coordenadas(x0, y0, posicion, posicion.es_oscura)

            if not activo:
                self.lienzo.create_rectangle(
                    x0, y0, x0 + LADO_CASILLA, y0 + LADO_CASILLA,
                    fill=FONDO, stipple="gray50", outline="",
                )
            if posicion in casillas_ultima:
                self.lienzo.create_rectangle(
                    x0, y0, x0 + LADO_CASILLA, y0 + LADO_CASILLA,
                    fill=ULTIMA, stipple="gray25", outline="",
                )
            if posicion == rey_en_jaque:
                self.lienzo.create_rectangle(
                    x0, y0, x0 + LADO_CASILLA, y0 + LADO_CASILLA,
                    fill=JAQUE, stipple="gray50", outline="",
                )
            if posicion == self.origen:
                self.lienzo.create_rectangle(
                    x0 + 2, y0 + 2, x0 + LADO_CASILLA - 2, y0 + LADO_CASILLA - 2,
                    outline=SELECCION, width=3,
                )

            pieza = tablero.obtener(posicion)
            if pieza is not None:
                self.lienzo.create_text(
                    centro_x, centro_y, text=pieza.simbolo, font=fuente,
                    fill="#ffffff" if pieza.color is Color.NEGRO else "#101010",
                )

            # Los destinos legales se marcan con un punto si están vacíos y con
            # un anillo si hay algo que capturar. La diferencia se ve de un
            # vistazo y evita tener que leer la pieza para saber si es una
            # captura.
            if posicion in destinos and posicion != self.origen:
                if pieza is not None:
                    self.lienzo.create_oval(
                        x0 + 4, y0 + 4, x0 + LADO_CASILLA - 4, y0 + LADO_CASILLA - 4,
                        outline=DESTINO_ACTIVO if activo else DESTINO_INACTIVO, width=4,
                    )
                else:
                    self.lienzo.create_oval(
                        centro_x - LADO_CASILLA / 9, centro_y - LADO_CASILLA / 9,
                        centro_x + LADO_CASILLA / 9, centro_y + LADO_CASILLA / 9,
                        fill=DESTINO_ACTIVO if activo else DESTINO_INACTIVO, outline="",
                    )

    def _pintar_coordenadas(self, x0: int, y0: int, posicion: Posicion, oscuro: bool) -> None:
        """Los números de fila y las letras de columna.

        Van por fuera del tablero de color y no encima de las casillas: si se
        pintaran encima quedarían tapados por las piezas y no se podría leer
        ninguna coordenada, que es justo lo que hace falta para clicar en la
        casilla correcta.

        La letra se escribe en la fila de casillas que queda *arriba* y *abajo*
        en pantalla, y se averigua con ``_a_pantalla`` en vez de con la columna:
        al girar el tablero la columna "a" pasa al otro lado, y si la letra se
        colocara por columna se vería arriba a la derecha en lugar de abajo.
        """
        color = CLARA if oscuro else OSCURA
        letra = posicion.notacion[0]
        self.lienzo.create_text(
            x0 - 6, y0 + LADO_CASILLA / 2, text=str(posicion.fila + 1),
            anchor="e", fill=color, font=("Consolas", 9),
        )
        _, fila_pantalla = self._a_pantalla(posicion)
        if fila_pantalla == 0:
            self.lienzo.create_text(
                x0 + LADO_CASILLA / 2, y0 - 6, text=letra,
                anchor="s", fill=color, font=("Consolas", 9),
            )
        elif fila_pantalla == 7:
            self.lienzo.create_text(
                x0 + LADO_CASILLA / 2, y0 + LADO_CASILLA + 6, text=letra,
                anchor="n", fill=color, font=("Consolas", 9),
            )

    def _fuente_de_piezas(self) -> tuple[str, int]:
        """La primera fuente instalada que tenga los símbolos de ajedrez.

        Sin ella el tablero sale con cuadrados vacíos, que es un fallo que no
        lanza ningún error: se ve un tablero en blanco y no se sabe por qué.
        """
        disponibles = set(tkfont.families(self.root))
        for nombre in ("Segoe UI Symbol", "DejaVu Sans", "Noto Sans Symbols 2", "Arial Unicode MS"):
            if nombre in disponibles:
                return (nombre, 34)
        return ("TkDefaultFont", 30)

    # ------------------------------------------------------------------
    # Interacción con el tablero
    # ------------------------------------------------------------------

    def _al_mover_el_raton(self, evento: tk.Event) -> None:
        """Marca la casilla señalada, para saber dónde se va a hacer clic."""
        posicion = self._de_pantalla(evento.x, evento.y)
        self.lienzo.delete("raton")
        if posicion is None:
            return
        columna, fila = self._a_pantalla(posicion)
        self.lienzo.create_rectangle(
            MARGEN + columna * LADO_CASILLA, MARGEN + fila * LADO_CASILLA,
            MARGEN + (columna + 1) * LADO_CASILLA, MARGEN + (fila + 1) * LADO_CASILLA,
            outline="#ffffff", width=2, tags="raton",
        )

    def _al_hacer_clic(self, evento: tk.Event) -> None:
        posicion = self._de_pantalla(evento.x, evento.y)
        if posicion is None:
            return

        partida = self.controlador.partida
        if partida.esta_terminada():
            self._anotar("La partida terminó. Use «Partida nueva» para empezar otra.")
            return

        pieza = partida.tablero.obtener(posicion)
        es_pieza_propia = (
            pieza is not None
            and (self.color is None or pieza.color is self.color)
            and pieza.color is partida.turno
        )

        # Sin nada seleccionado, el primer clic elige casilla.
        if self.origen is None:
            if pieza is None:
                return
            if self.color is not None and pieza.color is not self.color:
                self._anotar(f"Esa pieza es de las {pieza.color.nombre_legible.lower()}.")
                return
            if not es_pieza_propia:
                self._anotar("No es su turno todavía.")
                return
            # ``movimientos_de`` devuelve los movimientos **legales**, con el
            # enroque y la captura al paso ya resueltos y descartados los que
            # dejarían al rey en jaque. Es el mismo criterio que usa el
            # controlador para validar, así que lo que se ilumina es exactamente
            # lo que se puede jugar.
            self.origen = posicion
            self.destinos = partida.tablero.movimientos_de(posicion)
            if not self.destinos:
                self._anotar(
                    f"La pieza de {posicion.notacion} no puede moverse: "
                    "pondría en jaque a su propio rey."
                )
            self._pintar_tablero()
            return

        destinos = {movimiento.destino for movimiento in self.destinos}

        # Con algo seleccionado, si se hace clic en otra pieza propia se cambia
        # la selección en vez de intentar una jugada imposible.
        if es_pieza_propia and posicion not in destinos:
            self.origen = posicion
            self.destinos = partida.tablero.movimientos_de(posicion)
            self._pintar_tablero()
            return

        if posicion == self.origen:
            self.origen = None
            self.destinos = []
            self._pintar_tablero()
            return

        if posicion not in destinos:
            self._anotar(f"De {self.origen.notacion} no se puede ir a {posicion.notacion}.")
            self.origen = None
            self.destinos = []
            self._pintar_tablero()
            return

        origen, self.origen, self.destinos = self.origen, None, []
        self._jugar(origen, posicion)

    def _jugar(self, origen: Posicion, destino: Posicion) -> None:
        """Monta el texto de la jugada y se lo pasa al controlador.

        La ventana no sabe ninguna regla de ajedrez: solo construye
        ``"origen-destino"`` (más la letra de promoción si hace falta) y se lo
        entrega a ``aplicar_jugada``, que es quien decide si es legal. Si aquí
        hubiera una comprobación, habría dos verdades sobre qué es una jugada
        legal, y un día disagree y romperían.
        """
        letra = ""
        pieza = self.controlador.partida.tablero.obtener(origen)
        if pieza is not None and pieza.tipo is TipoPieza.PEON and destino.fila in (0, 7):
            tipo = self._elegir_promocion(pieza.color)
            if tipo is None:
                self._refrescar()  # cancelado: la partida sigue igual
                return
            letra = LETRA_DE_PROMOCION[tipo]

        self.controlador.aplicar_jugada(f"{origen.notacion}{destino.notacion}{letra}")
        self._refrescar()

    def _elegir_promocion(self, color: Color) -> TipoPieza | None:
        """Popup con las cuatro piezas a las que puede coronar el peón.

        Se dibujan con el símbolo de cada pieza, que es como se elige en cualquier
        programa de ajedrez, y no con cuatro botones de texto. ``None`` es
        cancelar, y cancelar tiene que ser posible: la promoción se puede
        deshacer con «Deshacer», pero si el popup no se puede cerrar la jugada se
        queda a medias.
        """
        elecida: dict[str, TipoPieza | None] = {"tipo": None}
        ventana = tk.Toplevel(self.root)
        ventana.title("Promoción")
        ventana.transient(self.root)
        ventana.resizable(False, False)
        ventana.grab_set()

        marco = ttk.Frame(ventana, padding=14)
        marco.grid()
        ttk.Label(marco, text="El peón coronará como:", font=("Segoe UI", 10)).grid(
            row=0, column=0, columnspan=4, pady=(0, 10)
        )

        def cerrar(tipo: TipoPieza | None) -> None:
            elecida["tipo"] = tipo
            ventana.destroy()

        fuente = self._fuente_de_piezas()
        for indice, tipo in enumerate(TIPOS_PROMOCION):
            # La pieza se enseña ya del color que va a tener, que es el del peón
            # que acaba de llegar.
            ttk.Label(marco, text=SIMBOLOS[(tipo, color)], font=fuente).grid(
                row=1, column=indice, padx=6
            )
            ttk.Button(
                marco, text=tipo.nombre_legible, width=9,
                command=lambda t=tipo: cerrar(t),
            ).grid(row=2, column=indice, padx=4, pady=(4, 0))

        ventana.bind("<Escape>", lambda _e: cerrar(None))
        ventana.protocol("WM_DELETE_WINDOW", lambda: cerrar(None))
        ventana.wait_window()
        return elecida["tipo"]

    # ------------------------------------------------------------------
    # Refresco de lo que no es el tablero
    # ------------------------------------------------------------------

    def _refrescar(self) -> None:
        partida = self.controlador.partida
        self._pintar_tablero()

        self.etiqueta_estado.configure(
            text=partida.estado.nombre_legible if partida.esta_terminada() else "En curso"
        )
        self.etiqueta_turno.configure(text=partida.resumen())

        self.campo_fen.delete(0, "end")
        self.campo_fen.insert(0, partida.a_fen())
        self._llenar_historial(partida)

        # Con la partida terminada no tiene sentido deshacer ni guardar nada más.
        terminada = partida.esta_terminada()
        for clave in ("deshacer", "guardar", "cargar", "borrar", "tablas", "abandonar"):
            self.botones[clave].configure(state="disabled" if terminada else "normal")

    def _llenar_historial(self, partida: Partida) -> None:
        self.historial.configure(state="normal")
        self.historial.delete("1.0", "end")
        lineas = partida.jugadas_en_notacion()
        if not lineas:
            self.historial.insert("end", "  (todavía no hay jugadas)")
        else:
            for linea in lineas:
                self.historial.insert("end", linea + "\n")
        self.historial.configure(state="disabled")
        self.historial.see("end")

    def _anotar(self, texto: str, error: bool = False) -> None:
        """Escribe un aviso en el panel y lo deja a la vista."""
        self.avisos.configure(state="normal")
        self.avisos.insert("end", texto + "\n", "error" if error else ())
        self.avisos.see("end")
        self.avisos.configure(state="disabled")

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------

    def _al_cambiar_color(self) -> None:
        anterior = self.color
        self.color = {"blancas": Color.BLANCO, "negras": Color.NEGRO, "ambas": None}[
            self.opciones_color.get()
        ]
        # El tablero se coloca solo con el color elegido abajo: quien juega con
        # negras ve sus piezas en su lado, que es como se juega de verdad. Con
        # "los dos colores" no hay bando propio, así que se deja como esté
        # (puede haber girado el tablero a mano con el botón).
        if self.color is not None:
            self.girada = self.color is Color.NEGRO
        # Cambiar de color cambia a quién le toca el ratón, así que la selección
        # en curso deja de tener sentido.
        self.origen = None
        self.destinos = []

        # El bando y el turno de la partida tienen que seguir de acuerdo. Si se
        # cambia el bando con la partida ya empezada, el turno se queda en el
        # color de antes y la partida vuelve a quedar bloqueada (ninguna jugada
        # sería legal: por el turno unas, por el bando las otras). Por eso se
        # vuelve a pasar por el controlador, que es quien pone las dos cosas en
        # su sitio. Preguntar antes es solo por no perder la partida en curso sin
        # querer.
        if self._hay_jugadas() and not self._confirmar_cambio_de_bando(anterior):
            # Se cancela el cambio: se vuelve al bando anterior, y también el
            # botón de radio, que si no se quedaría marcando lo que no es.
            self.color = anterior
            if anterior is not None:
                self.girada = anterior is Color.NEGRO
            self.opciones_color.set(self._clave_de_color(anterior))
            self._refrescar()
            return

        self.controlador.nueva_partida(self.color)
        self._refrescar()

    def _hay_jugadas(self) -> bool:
        """True si la partida ha empezado (o ya terminó) y se perdería al reiniciar."""
        partida = self.controlador.partida
        return bool(partida.historial) or partida.esta_terminada()

    def _clave_de_color(self, color: Color | None) -> str:
        """El valor del botón de radio que corresponde a un color."""
        if color is Color.NEGRO:
            return "negras"
        if color is Color.BLANCO:
            return "blancas"
        return "ambas"

    def _confirmar_cambio_de_bando(self, anterior: Color | None) -> bool:
        """Pregunta si se puede cambiar de bando teniendo la partida empezada."""
        antes = self._clave_de_color(anterior)
        return bool(
            messagebox.askyesno(
                "Cambiar de bando",
                f"La partida tiene jugadas y cambiarla de bando la reinicia.\n\n"
                f"¿Empezar una partida nueva jugando con {antes}?",
                parent=self.root,
            )
        )

    def _girar(self) -> None:
        self.girada = not self.girada
        self._refrescar()

    def _nueva_partida(self) -> None:
        # Se llama al controlador y no se reinicia la partida a mano. La
        # diferencia no es de estilo: el controlador es quien tiene que poner de
        # acuerdo el bando elegido con el turno inicial (si juegas con negras,
        # empiezan las negras), y si la vista reinicia por su cuenta se queda
        # sin esa mitad y la partida vuelve a bloquearse.
        self.controlador.nueva_partida(self.color)
        self.origen = None
        self.destinos = []
        self._anotar("Partida nueva.")
        self._refrescar()

    def _deshacer(self) -> None:
        self.controlador.deshacer()
        self.origen = None
        self.destinos = []
        self._refrescar()

    def _tablas(self) -> None:
        self.controlador.empatar()
        self._refrescar()

    def _abandonar(self) -> None:
        self.controlador.abandonar()
        self._refrescar()

    def _copiar_fen(self) -> None:
        self.campo_fen.selection_range(0, "end")
        self.campo_fen.focus_set()
        self.root.clipboard_clear()
        self.root.clipboard_append(self.controlador.partida.a_fen())
        self._anotar("FEN copiado al portapapeles.")

    def _guardar(self) -> None:
        if self.storage is None:
            self._anotar("No hay almacenamiento configurado.", error=True)
            return
        nombre = self._preguntar_texto(
            "Guardar partida", "Nombre de la partida", "Partida sin nombre"
        )
        if nombre is None:
            self._anotar("Guardado cancelado.")
            return
        if self.controlador.guardar(nombre):
            self._anotar("Guardada.")

    def _cargar(self) -> None:
        if self.storage is None:
            self._anotar("No hay almacenamiento configurado.", error=True)
            return
        informes = self.controlador.listar_guardadas()
        if not informes:
            self._anotar("No hay ninguna partida guardada.")
            return
        clave = self._elegir_de_lista(
            "Cargar partida", "Elija la partida que quiere cargar", self._filas(informes)
        )
        if clave is None:
            return
        if self.controlador.cargar(clave):
            self.origen = None
            self.destinos = []
            self._refrescar()

    def _listar(self) -> None:
        informes = self.controlador.listar_guardadas()
        if not informes:
            self._anotar("No hay ninguna partida guardada.")
            return
        self._elegir_de_lista(
            "Partidas guardadas", "Estas son las partidas guardadas",
            self._filas(informes), solo_lectura=True,
        )

    def _borrar(self) -> None:
        if self.storage is None:
            self._anotar("No hay almacenamiento configurado.", error=True)
            return
        informes = self.controlador.listar_guardadas()
        if not informes:
            self._anotar("No hay ninguna partida guardada.")
            return
        clave = self._elegir_de_lista(
            "Borrar partida", "Elija la partida que quiere borrar", self._filas(informes)
        )
        if clave is None:
            return
        if not messagebox.askyesno("Confirmar", f"¿Borrar la partida {clave}?", parent=self.root):
            return
        if self.controlador.eliminar_guardada(clave):
            self._refrescar()

    @staticmethod
    def _filas(informes: list[dict]) -> list[tuple[str, str]]:
        return [
            (
                informe["id"],
                f"{informe.get('fecha', ''):<20}{informe.get('resultado', ''):<12}"
                f"{informe.get('nombre', '')}",
            )
            for informe in informes
        ]

    # ------------------------------------------------------------------
    # Diálogos auxiliares (rápidos, no menús)
    # ------------------------------------------------------------------

    def _preguntar_texto(self, titulo: str, etiqueta: str, por_defecto: str) -> str | None:
        respuesta: dict[str, str | None] = {"valor": None}
        ventana = tk.Toplevel(self.root)
        ventana.title(titulo)
        ventana.transient(self.root)
        ventana.resizable(False, False)
        ventana.grab_set()

        marco = ttk.Frame(ventana, padding=14)
        marco.grid()
        ttk.Label(marco, text=etiqueta).grid(row=0, column=0, sticky="w", pady=(0, 6))
        entrada = ttk.Entry(marco, width=44)
        entrada.insert(0, por_defecto)
        entrada.grid(row=1, column=0)
        entrada.focus_set()
        entrada.select_range(0, "end")

        def cerrar(valor: str | None) -> None:
            respuesta["valor"] = valor
            ventana.destroy()

        ventana.bind("<Return>", lambda _e: cerrar(entrada.get().strip() or None))
        ventana.bind("<Escape>", lambda _e: cerrar(None))
        ventana.protocol("WM_DELETE_WINDOW", lambda: cerrar(None))

        botones = ttk.Frame(marco)
        botones.grid(row=2, column=0, sticky="e", pady=(10, 0))
        ttk.Button(botones, text="Guardar", command=lambda: cerrar(entrada.get().strip() or None)).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(botones, text="Cancelar", command=lambda: cerrar(None)).grid(row=0, column=1)

        ventana.wait_window()
        return respuesta["valor"]

    def _elegir_de_lista(
        self,
        titulo: str,
        etiqueta: str,
        elementos: list[tuple[str, str]],
        solo_lectura: bool = False,
    ) -> str | None:
        elegido: dict[str, str | None] = {"clave": None}
        ventana = tk.Toplevel(self.root)
        ventana.title(titulo)
        ventana.transient(self.root)
        ventana.grab_set()

        marco = ttk.Frame(ventana, padding=14)
        marco.grid()
        ttk.Label(marco, text=etiqueta).grid(row=0, column=0, sticky="w", pady=(0, 6))

        lista = tk.Listbox(
            marco, width=78, height=min(14, max(4, len(elementos))), font=("Consolas", 9)
        )
        lista.grid(row=1, column=0, sticky="ew")
        for clave, texto in elementos:
            lista.insert("end", f"{clave}  {texto}")
        lista.selection_set(0)

        def cerrar(clave: str | None) -> None:
            elegido["clave"] = clave
            ventana.destroy()

        def aceptar() -> None:
            seleccion = lista.curselection()
            cerrar(elementos[seleccion[0]][0] if seleccion else None)

        ventana.bind("<Return>", lambda _e: aceptar())
        ventana.bind("<Double-Button-1>", lambda _e: aceptar())
        ventana.bind("<Escape>", lambda _e: cerrar(None))
        ventana.protocol("WM_DELETE_WINDOW", lambda: cerrar(None))

        botones = ttk.Frame(marco)
        botones.grid(row=2, column=0, sticky="e", pady=(10, 0))
        if not solo_lectura:
            ttk.Button(botones, text="Aceptar", command=aceptar).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(botones, text="Cerrar", command=lambda: cerrar(None)).grid(row=0, column=1)

        ventana.wait_window()
        return elegido["clave"]
