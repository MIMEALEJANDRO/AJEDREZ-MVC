"""Pintar: el tablero, las coordenadas, el FEN y el historial.

Todo lo que dibuja, y nada de lo que decide. Este módulo no sabe por qué se
pinta ni qué debe pasar al hacer clic: sabe cómo poner un rectángulo en su
casilla y cómo escribir una línea en una etiqueta.

Dos grupos:

* **El tablero**: dónde cae cada casilla en píxeles (``_a_pantalla`` y
  ``_de_pantalla``, que son el mismo cálculo en las dos direcciones) y el
  recorrido que se pinta. Que el dibujo y el clic usen la *misma* función es lo
  que evita el fallo más caro de una ventana de ajedrez: ver una casilla en un
  sitio y que el clic de ese sitio mueva otra. Está comprobado en
  ``tests/test_ventana_mapeo.py``.
* **Lo que no es el tablero**: la etiqueta de la última jugada, el FEN y el
  historial. Se rellenan al refrescar, y el panel de FEN solo si está abierto
  (que lo decide ``views/ventana_widgets.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from tkinter import font as tkfont

from models.enums import Color
from models.partida import Partida
from models.posicion import Posicion
from views.ventana_widgets import (
    CLARA,
    DESTINO_ACTIVO,
    DESTINO_INACTIVO,
    FONDO,
    JAQUE,
    LADO_CASILLA,
    MARGEN,
    OSCURA,
    SELECCION,
    TEXTO,
    ULTIMA,
)




class DibujoVentana:
    """Mezcla de dibujo: ver el docstring del módulo."""

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

        # Cuando no es tu turno el tablero se atenúa. La pregunta "quién puede
        # mover" se la hace al controlador, que es quien tiene la regla, en vez
        # de repetirla aquí: así el tablero y los clics no pueden discrepar.
        activo = self.controlador.color_que_juega() is not None

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
                    fill="#101010" if pieza.color is Color.NEGRO else "#fff4cc",
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
    def _refrescar_ultima_jugada(self, partida: Partida) -> None:
        """Escribe en una línea qué fue lo último que se jugó.

        Con el historial entero a la vista era difícil saber qué acabas de hacer;
        esto lo dice sin más. Se deduce del último movimiento del historial y del
        turno: como el turno ya es el del siguiente cuando se mira, quien movió
        es su contrario.
        """
        if not partida.historial:
            self.etiqueta_ultima.configure(text="Todavía no hay jugadas")
            return
        movimiento = partida.historial[-1]
        color = partida.turno.contrario
        self.etiqueta_ultima.configure(
            text=f"{color.nombre_legible} {movimiento.notacion}"
        )
    def _refrescar_panel_fen(self, partida: Partida) -> None:
        """Rellena el FEN y el historial. Solo tiene efecto si el panel está abierto.

        Se comprueba la visibilidad para no escribir en unas 40 casillas de
        historial que no se están viendo. Es una economía pequeña, pero lo que
        importa es que el contenido se pone al día al abrirlo y en cada jugada
        mientras esté abierto, y en ningún otro momento puede quedar viejo.
        """
        if not self._panel_fen_visible:
            return
        self.campo_fen.delete(0, "end")
        self.campo_fen.insert(0, partida.a_fen())
        self._llenar_historial(partida)
    def _refrescar(self) -> None:
        partida = self.controlador.partida
        self._pintar_tablero()

        self.etiqueta_estado.configure(
            text=partida.estado.nombre_legible if partida.esta_terminada() else "En curso"
        )
        self.etiqueta_turno.configure(text=partida.resumen())

        self._refrescar_ultima_jugada(partida)
        self._refrescar_panel_fen(partida)

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
