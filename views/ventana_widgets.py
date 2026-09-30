"""Construcción de la ventana: qué widgets hay y cómo se colocan.

Este módulo tiene la mitad "estructural" de la ventana jugable: crea el árbol de
widgets (lienzo, panel lateral, botones, el panel de FEN) y sabe mostrarlos y
ocultarlos. También vive aquí la configuración que decide cómo se ve el tablero
—el lado de la casilla, los colores, el margen— y **el bando por defecto**.

Está separado del dibujo y de los eventos por una razón práctica: son tres
cambios que se hacen por motivos distintos y a manos distintas. Retocar el color
de una casilla, añadir un botón o cambiar quién puede mover no se tocan entre sí.

El resto de la ventana está en:

* ``views/ventana_dibujo.py`` — pintar el tablero y refrescar los paneles.
* ``views/ventana_eventos.py`` — qué pasa al hacer clic o al pulsar un botón.
* ``views/ventana.py`` — la clase ``VentanaAjedrez``, que es la que las junta.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from controllers.partida_controller import PartidaController
from models.enums import Color, TipoPieza
from models.partida import Partida
from storage.base_storage import BaseStorage

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

CLAVE_BANDO = {Color.BLANCO: "blancas", Color.NEGRO: "negras", None: "ambas"}
INVERSO_BANDO = {texto: color for color, texto in CLAVE_BANDO.items()}

# --------------------------------------------------------------------------
# EL BANDO POR DEFECTO
# --------------------------------------------------------------------------
# Esta es la línea que decide con qué color se juega al abrir el programa, y es
# la primera que hay que mirar si alguna vez hay que cambiarla.
#
# Poner ``Color.BLANCO`` (y no ``None``) es deliberado, y la diferencia se nota a
# la primera jugada. Como en ajedrez **siempre mueven las blancas primero**:
#
#   BANDO_POR_DEFECTO = Color.BLANCO  -> se puede jugar e2e4 y ahí se acaba.
#   BANDO_POR_DEFECTO = None          -> se juega la partida entera con los dos
#                                      bandos, porque no hay bando que esperar.
#
# Es decir: con un bando elegido solo se mueve la jugada que le toca a ese bando,
# que es exactamente lo que pide el reglamento. Para practicar una partida
# completa hay que elegir "Los dos colores" en el panel.
BANDO_POR_DEFECTO: Color | None = Color.BLANCO

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


class WidgetsVentana:
    """Mezcla de widgets: ver el docstring del módulo."""

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
        # El botón de radio se pone en el bando por defecto, y el texto del
        # botón sale del mismo diccionario, así que el selector y la partida
        # siempre coinciden.
        self.opciones_color = tk.StringVar(panel, value=CLAVE_BANDO[BANDO_POR_DEFECTO])
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

        # -- última jugada --
        # Lo único sobre la partida que se ve sin pedir nada. Antes esto no
        # estaba: el panel enseñaba el historial entero y el FEN de golpe, que es
        # mucha información para lo que se quiere de verdad al mover una pieza
        # ("qué acabo de hacer"). El historial completo y el FEN siguen estando,
        # pero detrás del botón de más abajo.
        ttk.Label(panel, text="Última jugada:", font=("Segoe UI", 9, "bold")).grid(
            row=4, column=0, sticky="w"
        )
        self.etiqueta_ultima = ttk.Label(panel, text="Todavía no hay jugadas", font=("Segoe UI", 9))
        self.etiqueta_ultima.grid(row=5, column=0, sticky="w", pady=(2, 10))

        # -- botón que abre y cierra el detalle --
        self.boton_fen = ttk.Button(panel, text="Mostrar FEN", command=self._alternar_panel_fen)
        self.boton_fen.grid(row=6, column=0, sticky="ew", pady=(0, 12))

        # -- el detalle: FEN e historial, oculto de entrada --
        # Se construye entero pero **nace sin hacer grid**: por eso no se ve
        # nada hasta que se pulsa el botón. ``_panel_fen_visible`` es la que
        # manda, y se actualiza en los dos métodos de mostrar y ocultar, para no
        # tener que preguntarle a tkinter si algo está en pantalla.
        self._panel_fen_visible = False
        self.panel_fen = ttk.Frame(panel)
        ttk.Label(self.panel_fen, text="FEN", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.campo_fen = ttk.Entry(self.panel_fen, font=("Consolas", 9))
        self.campo_fen.grid(row=1, column=0, sticky="ew", pady=(2, 4))
        ttk.Button(self.panel_fen, text="Copiar FEN", command=self._copiar_fen).grid(
            row=2, column=0, sticky="ew"
        )
        ttk.Label(self.panel_fen, text="Jugadas", font=("Segoe UI", 9, "bold")).grid(
            row=3, column=0, sticky="w", pady=(12, 0)
        )
        self.historial = tk.Text(
            self.panel_fen, width=32, height=12, wrap="word", font=("Consolas", 10)
        )
        barra = ttk.Scrollbar(self.panel_fen, orient="vertical", command=self.historial.yview)
        self.historial.configure(yscrollcommand=barra.set, state="disabled")
        self.historial.grid(row=4, column=0, sticky="nsew", pady=(2, 0))
        barra.grid(row=4, column=1, sticky="ns")

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
            boton.grid(row=7 + fila, column=columna, sticky="ew", padx=(0, 5), pady=2)
            self.botones[clave] = boton
        filas_botones = 7 + (len(acciones) + 1) // 2

        # -- avisos --
        ttk.Label(panel, text="Avisos", font=("Segoe UI", 9, "bold")).grid(
            row=filas_botones, column=0, sticky="w", pady=(12, 0)
        )
        self.avisos = tk.Text(panel, width=32, height=6, wrap="word", font=("Segoe UI", 9))
        self.avisos.grid(row=filas_botones + 1, column=0, sticky="ew")
        self.avisos.tag_configure("error", foreground="#ff8080")

        panel.columnconfigure(0, weight=1)
        self.root.minsize(720, 580)
    def _mostrar_panel_fen(self) -> None:
        """Enseña el panel de FEN e historial y pone el botón en "Ocultar FEN"."""
        self.panel_fen.grid(row=6, column=0, sticky="nsew", pady=(0, 12))
        self.boton_fen.configure(text="Ocultar FEN")
        self._panel_fen_visible = True
        # Se rellena al abrirlo, no solo al mover: así nunca se puede ver un
        # FEN o un historial de la jugada anterior.
        self._refrescar_panel_fen(self.controlador.partida)
    def _ocultar_panel_fen(self) -> None:
        """Esconde el panel y vuelve a poner el botón en "Mostrar FEN"."""
        self.panel_fen.grid_remove()
        self.boton_fen.configure(text="Mostrar FEN")
        self._panel_fen_visible = False
