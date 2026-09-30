"""Qué pasa cuando la persona hace algo: clics, botones y diálogos.

La otra mitad de la ventana: aquí vive todo lo que **reacciona**. Un clic en una
casilla, un botón, un diálogo de confirmación.

La regla que sigue este módulo es la del proyecto entero: **la ventana no sabe
ninguna regla de ajedrez**. Comprobar si una jugada es legal es cosa del
controlador y del modelo. Lo que sí hace la ventana es decidir *qué se ha
pulsado* y contárselo: ``_jugar`` monta el texto ``"e2e4"`` y se lo pasa a
``controlador.aplicar_jugada``, sin decidir nada. Si aquí hubiera una
comprobación de reglas habría dos verdades sobre qué es una jugada legal, y un
día discreparían.

Tampoco decide quién puede mover: eso está en
``PartidaController.color_que_juega``, y la ventana solo se lo pregunta.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from models.enums import Color, TipoPieza
from models.pieza import SIMBOLOS, TIPOS_PROMOCION
from models.posicion import Movimiento, Posicion
from views.interfaz import texto_del_error
from views.ventana_widgets import (
    CLAVE_BANDO,
    INVERSO_BANDO,
    LADO_CASILLA,
    LETRA_DE_PROMOCION,
    MARGEN,
)




class EventosVentana:
    """Mezcla de eventos: ver el docstring del módulo."""

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
        es_pieza_propia = self.controlador.puede_mover_pieza(pieza)

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
    def _alternar_panel_fen(self) -> None:
        """Muestra u oculta el detalle de FEN e historial."""
        if self._panel_fen_visible:
            self._ocultar_panel_fen()
        else:
            self._mostrar_panel_fen()
    def _al_cambiar_color(self) -> None:
        # Cambiar de bando NO toca la partida. Antes sí lo hacía, y hacía falta
        # preguntar antes de reiniciar, porque el turno inicial dependía del bando
        # y se descuadraba. Ya no depende: el turno inicial es siempre el de las
        # blancas, que es una regla del ajedrez, así que cambiar de bando solo
        # cambia a quién le toca el ratón y nada más.
        self.color = INVERSO_BANDO[self.opciones_color.get()]
        # El tablero se coloca solo con el color elegido: quien juega con negras
        # ve sus piezas en su lado, que es como se juega de verdad. Con "los dos
        # colores" no hay bando propio, así que se deja como esté (puede haber
        # girado el tablero a mano con el botón).
        if self.color is not None:
            self.girada = self.color is Color.NEGRO
        # Se le dice al controlador cuál es el bando, para que sea él quien diga
        # si ahora se puede mover algo (ver ``color_que_juega``). La partida se
        # queda como está, con sus jugadas.
        self.controlador.color_jugador = self.color
        # Cambiar de color cambia a quién le toca el ratón, así que la selección
        # en curso deja de tener sentido.
        self.origen = None
        self.destinos = []
        self._refrescar()
    def _girar(self) -> None:
        self.girada = not self.girada
        self._refrescar()
    def _nueva_partida(self) -> None:
        # Se llama al controlador en vez de reiniciar la partida a mano, porque
        # el controlador es quien guarda el bando con el que se está jugando.
        self.controlador.nueva_partida(self.color)
        # El detalle se esconde: si estaba abierto enseñando las jugadas de la
        # partida anterior, dejarlo abiertoaría mostrando un historial que ya no
        # es el de esta partida.
        self._ocultar_panel_fen()
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
            # Por lo mismo que al empezar una partida: el detalle se esconde para
            # no dejar a la vista el historial de la partida que se acaba de
            # dejar. Se rellena al volver a abrirlo.
            self._ocultar_panel_fen()
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
