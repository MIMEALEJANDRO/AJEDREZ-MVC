"""Vista de ventana (tkinter): la segunda implementación de la vista.

Es la demostración de que el contrato funciona. ``PartidaView`` (consola) y
``VistaGUI`` (ventana) son dos clases sin relación de herencia entre ellas, con
métodos distintos y estructuras internas distintas, y las dos son vistas porque
las dos cumplen ``views.interfaz.InterfazVista``. El controlador no cambió ni
una línea al aparecer esta.

Reparto del trabajo entre las dos piezas:

* ``views/hilo.py`` (``PuenteHilos``) pone el controlador en un hilo aparte y
  avisa de cuándo termina.
* Esta clase reparte entre hilos: dibujar es cosa del hilo principal, y preguntar
  es abrir un diálogo y esperar.

Y aquí está el punto que hace que todo esto no sea un truco: **esta vista
también bloquea**. Sus menús y sus preguntas son diálogos modales, y el
controlador sigue esperando en un ``input()`` equivalente. Se escribió así a
propósito, porque es lo que permite reutilizar el controlador tal cual.

Si algún día se quieren botones de verdad, sin diálogos, el cambio queda
localizado en la sección "Preguntar" de este archivo: son los **ocho** métodos
que esperan, y cada uno devolvería su respuesta con un ``send()`` a un
generador en vez de esperar a un ``wait_window()``. Ni el controlador ni el
resto de la vista se tocarían.

Para arrancarla, ``main_gui.py`` en la raíz del proyecto.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from models.enums import Color
from models.partida import Partida
from models.posicion import Posicion
from views.hilo import PuenteHilos
from views.interfaz import (
    OPCIONES_ARCHIVO,
    OPCIONES_INICIO,
    OPCIONES_PARTIDA,
    InterfazVista,
    texto_del_error,
)

# Lado de cada casilla del tablero, en píxeles.
LADO_CASILLA = 44
# Margen alrededor del tablero para que las coordenadas no queden pegadas.
MARGEN = 16
# Colores de las casillas y del fondo.
CLARA = "#e8d3b0"
OSCURA = "#a97a52"
FONDO = "#2b2b2b"
CLARO = "#f0f0f0"


class VistaGUI(InterfazVista):
    """Ventana con el tablero, el registro de mensajes y los diálogos.

    Cómo se relaciona con el hilo del controlador:

    * ``escribir`` y compañía no esperan: solo piden al hilo principal que
      pinten y devuelven enseguida, para que el controlador siga avanzando.
    * ``pedir_jugada`` y compañía sí esperan: abren un diálogo y se quedan
      esperando a que alguien conteste.

    Las dos cosas pasan por ``_en_hilo_principal``, que detecta si la llamada
    llega del hilo de la interfaz o del de trabajo. En el primer caso se hace
    directamente; en el segundo se encola con ``root.after`` y, si hace falta,
    se espera con un ``Event``.

    Sin puente (en las pruebas, por ejemplo) todo ocurre en el hilo principal y
    el puente no se usa nunca: los métodos funcionan igual sin cambiar una línea.
    """

    OPCIONES_INICIO = OPCIONES_INICIO
    OPCIONES_PARTIDA = OPCIONES_PARTIDA
    OPCIONES_ARCHIVO = OPCIONES_ARCHIVO

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        # El puente lo inyecta quien arranca. Es ``None`` cuando la vista se
        # usa sola, y entonces todos los métodos trabajan en el hilo principal
        # sin necesidad de encolar nada.
        self.puente: PuenteHilos | None = None
        self._construir()

    # ------------------------------------------------------------------
    # Estructura de la ventana
    # ------------------------------------------------------------------

    def _construir(self) -> None:
        """Monta la ventana. Solo toca el hilo principal."""
        self.root.title("Ajedrez")
        self.root.configure(background=FONDO)

        marco = ttk.Frame(self.root, padding=10)
        marco.grid(row=0, column=0, sticky="nsew")

        self.lienzo = tk.Canvas(
            marco,
            width=LADO_CASILLA * 8 + MARGEN * 2,
            height=LADO_CASILLA * 8 + MARGEN * 2,
            background=FONDO,
            highlightthickness=0,
        )
        self.lienzo.grid(row=0, column=0, sticky="nsew")

        self.etiqueta_estado = tk.Label(
            marco, text="", background=FONDO, foreground=CLARO, anchor="w"
        )
        self.etiqueta_estado.grid(row=1, column=0, sticky="ew", pady=(10, 4))

        registro = ttk.LabelFrame(marco, text="Mensajes", padding=6)
        registro.grid(row=2, column=0, sticky="ew")
        self.texto = tk.Text(registro, width=52, height=14, wrap="word", font=("Consolas", 10))
        barra = ttk.Scrollbar(registro, orient="vertical", command=self.texto.yview)
        self.texto.configure(yscrollcommand=barra.set, state="disabled")
        self.texto.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        # Los "tags" son la forma más barata de tener texto de color sin montar
        # un panel de formato entero.
        self.texto.tag_configure("error", foreground="#ff6b6b")
        self.texto.tag_configure("aviso", foreground="#ffd166")

        self.root.minsize(LADO_CASILLA * 8 + MARGEN * 2 + 40, 520)

    # ------------------------------------------------------------------
    # El puente entre hilos
    # ------------------------------------------------------------------

    def _en_hilo_principal(self, accion: Callable[[], Any], esperar: bool) -> Any:
        """Ejecuta ``accion`` en el hilo de la interfaz, y quizá espera.

        Es el único punto de la vista que sabe de hilos, y está aquí a
        propósito. El planificador (``root.after``) es lo que garantiza que el
        código toca la ventana desde el hilo único que puede tocarla.

        Con ``esperar=False`` se encola y se devuelve ``None``: es lo que
        necesitan todos los métodos que pintan, porque el controlador debe poder
        seguir avanzando mientras la ventana se redibuja.

        Con ``esperar=True`` se encola igual, pero se bloquea hasta que la
        acción haya terminado. El valor vuelve en una ``caja`` y no como
        resultado de ``after``, porque ``after`` es un planificador y no
        devuelve el resultado de nada.
        """
        if self.puente is None or self.puente.en_hilo_principal():
            return accion()
        if not esperar:
            self.root.after(0, accion)
            return None
        caja: dict[str, Any] = {}
        listo = threading.Event()

        def correr() -> None:
            try:
                caja["valor"] = accion()
            except BaseException as error:  # noqa: BLE001 - se devuelve, no se traga
                caja["error"] = error
            finally:
                listo.set()

        self.root.after(0, correr)
        listo.wait()
        if "error" in caja:
            raise caja["error"]
        return caja.get("valor")

    def _pintar(self, metodo: Callable[..., Any], *args: Any) -> None:
        """Ejecuta un método de pintado sin esperar. Para uso interno."""
        self._en_hilo_principal(lambda: metodo(*args), esperar=False)

    # ------------------------------------------------------------------
    # Diálogos: lo único que espera
    # ------------------------------------------------------------------

    def _dialogo(
        self,
        titulo: str,
        cuerpo: str,
        por_defecto: str = "",
        opciones: dict[str, str] | None = None,
    ) -> str | None:
        """Abre una ventana modal y devuelve lo que se elija, o ``None``.

        El diálogo se construye *en el hilo principal* (por eso lo envuelve
        ``_en_hilo_principal``) y usa ``wait_window``, que es el bucle de
        eventos de tkinter. Quien espera al resultado es el hilo del
        controlador, y espera en su ``Event.wait()``. Cada uno en el suyo.

        ``opciones`` distingue los dos tipos de diálogo:

        * Con opciones: un radiobotón por opción y "Aceptar". Es un menú.
        * Sin opciones: un campo de texto y "Aceptar"/"Cancelar". Es una
          pregunta.
        """
        return self._en_hilo_principal(
            lambda: self._dialogo_real(titulo, cuerpo, por_defecto, opciones),
            esperar=True,
        )

    def _dialogo_real(
        self,
        titulo: str,
        cuerpo: str,
        por_defecto: str,
        opciones: dict[str, str] | None,
    ) -> str | None:
        """Construye el diálogo y espera a que se cierre. Hilo principal."""
        ventana = tk.Toplevel(self.root)
        ventana.title(titulo)
        ventana.transient(self.root)
        ventana.resizable(False, False)
        # ``grab_set`` es lo que lo convierte en *modal*: mientras esté abierto,
        # la ventana principal no recibe ni clics ni teclado. Sin él se podría
        # pulsar "Guardar" dos veces seguidas.
        ventana.grab_set()

        marco = ttk.Frame(ventana, padding=14)
        marco.grid()
        ttk.Label(marco, text=cuerpo, wraplength=430, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        respuesta: dict[str, str | None] = {"valor": None}
        # Fila donde empieza el contenido (los radiobotones o el campo), y fila
        # donde van los botones. Se calculan antes de colocar nada para que los
        # botones no se muevan al cambiar el número de opciones.
        fila_contenido = 1
        fila_botones = 2

        if opciones is not None:
            # -- diálogo de menú: un radiobotón por opción --
            seleccion = tk.StringVar(marco, value=por_defecto or next(iter(opciones)))
            for indice, (clave, texto) in enumerate(opciones.items()):
                ttk.Radiobutton(
                    marco, text=f"{clave}. {texto}", value=clave, variable=seleccion
                ).grid(row=fila_contenido + indice, column=0, columnspan=2, sticky="w")
            fila_botones = fila_contenido + len(opciones)
        else:
            # -- diálogo de texto: un campo y aceptar/cancelar --
            entrada = ttk.Entry(marco, width=46)
            entrada.insert(0, por_defecto)
            entrada.grid(row=fila_contenido, column=0, columnspan=2, sticky="ew", pady=(0, 6))
            entrada.focus_set()
            # Seleccionar todo lo escrito es lo que hace cómodo pulsar Enter:
            # sustituye de un golpe en vez de tener que borrarlo antes.
            entrada.select_range(0, "end")

        def cerrar(valor: str | None) -> None:
            respuesta["valor"] = valor
            ventana.destroy()

        if opciones is not None:
            def aceptar() -> None:
                cerrar(seleccion.get())
        else:
            def aceptar() -> None:
                cerrar(entrada.get())

        ventana.bind("<Return>", lambda _e: aceptar())
        ventana.bind("<Escape>", lambda _e: cerrar(None))
        ventana.protocol("WM_DELETE_WINDOW", lambda: cerrar(None))

        marco_botones = ttk.Frame(marco)
        marco_botones.grid(row=fila_botones, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(marco_botones, text="Aceptar", command=aceptar).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(marco_botones, text="Cancelar", command=lambda: cerrar(None)).grid(
            row=0, column=1
        )

        ventana.wait_window()
        return respuesta["valor"]

    # ------------------------------------------------------------------
    # Pintar (nueve métodos que no esperan)
    # ------------------------------------------------------------------

    def escribir(self, texto: str = "") -> None:
        self._pintar(self._escribir, texto)

    def _escribir(self, texto: str, color: str | None = None) -> None:
        self.texto.configure(state="normal")
        self.texto.insert("end", texto + "\n", color)
        # Con miles de líneas más tarde esto sigue haciendo falta: insertar al
        # final deja la vista arriba, que es lo contrario de lo que quiere
        # quien está leyendo.
        self.texto.see("end")
        self.texto.configure(state="disabled")

    def titulo(self, texto: str) -> None:
        self._pintar(self._escribir, "")
        self._pintar(self._escribir, f"── {texto} " + "─" * max(4, 42 - len(texto)))

    def mostrar_mensaje(self, mensaje: str) -> None:
        self._pintar(self._escribir, f"  {mensaje}", "aviso")

    def mostrar_error(self, error: Exception | str) -> None:
        self._pintar(self._escribir, f"  {texto_del_error(error)}", "error")

    def mostrar_ayuda(self) -> None:
        self._pintar(
            self._escribir,
            "\n".join(
                [
                    "  Cómo se juega",
                    "    Una jugada se escribe con origen y destino pegados:",
                    "        e2e4, e2-e4 o 'e2 e4'.",
                    "    Un peón que llega al final necesita promoción:",
                    "        a7a8q  (q = dama, r = torre, b = alfil, n = caballo).",
                    "    Enroque: e1g1 con el rey y la torre en su sitio,",
                    "        y sin estar en jaque ni pasar por una casilla atacada.",
                ]
            ),
        )

    def mostrar_partidas(self, informes: list[dict]) -> None:
        if not informes:
            self.mostrar_mensaje("(no hay ninguna partida guardada)")
            return
        self._pintar(self._escribir, f"  {'Clave':<34}{'Fecha':<22}{'Estado':<14}Nombre")
        for informe in informes:
            self._pintar(
                self._escribir,
                f"  {informe['id']:<34}{informe.get('fecha', ''):<22}"
                f"{informe.get('resultado', ''):<14}{informe.get('nombre', '')}",
            )

    def mostrar_historial(self, partida: Partida) -> None:
        lineas = partida.jugadas_en_notacion()
        if not lineas:
            self.mostrar_mensaje("(todavía no hay jugadas)")
            return
        for linea in lineas:
            self._pintar(self._escribir, f"  {linea}")

    def mostrar_fen(self, partida: Partida) -> None:
        self._pintar(self._escribir, f"  {partida.a_fen()}")

    def mostrar_tablero(self, partida: Partida) -> None:
        self._pintar(self._pintar_tablero, partida)

    def _pintar_tablero(self, partida: Partida) -> None:
        """Dibuja las 64 casillas con su pieza, y el estado debajo.

        Se borra el lienzo entero y se redibuja. Podría usarse
        ``itemconfigure`` para no tocar lo que no cambia, pero a 64 casillas el
        coste es despreciable y el código queda la mitad de corto: en cada
        jugada cambia el tablero entero, no un cuadrado suelto.

        El borrado es ``delete("all")`` porque en un canvas de Tk todos los
        elementos pertenecen a la etiqueta "all"; ``delete("todo")`` no borra
        nada, porque "todo" no es una etiqueta que exista, y el tablero se
        acabaría apilando sobre el anterior.
        """
        self.lienzo.delete("all")
        fuente = self._fuente_de_piezas()
        # La fila 0 del modelo es la primera (las blancas abajo) y en pantalla
        # va abajo, así que se invierte al pintar. Es el mismo criterio que usa
        # ``Tablero.__str__`` para la consola.
        for fila_pantalla in range(8):
            fila = 7 - fila_pantalla
            for columna in range(8):
                x0 = MARGEN + columna * LADO_CASILLA
                y0 = MARGEN + fila_pantalla * LADO_CASILLA
                # El color de la casilla lo dice el modelo (``es_oscura``, con
                # a1 oscura) y no un ``(fila + columna) % 2`` de la vista: si el
                # modelo cambiara su criterio, la vista lo seguiría sin tener
                # que acordarse de nada.
                oscuro = Posicion(columna, fila).es_oscura
                self.lienzo.create_rectangle(
                    x0, y0, x0 + LADO_CASILLA, y0 + LADO_CASILLA,
                    fill=OSCURA if oscuro else CLARA,
                    outline="",
                )
                self._pintar_coordenadas(x0, y0, fila, columna, oscuro)
                pieza = partida.tablero.obtener(Posicion(columna, fila))
                if pieza is not None:
                    self.lienzo.create_text(
                        x0 + LADO_CASILLA / 2,
                        y0 + LADO_CASILLA / 2,
                        text=pieza.simbolo,
                        font=fuente,
                        # Al revés que el color de la pieza: la blanca es un
                        # hueco y la negra un disco, así que la negra necesita
                        # texto claro para verse sobre una casilla oscura.
                        fill=CLARO if pieza.color is Color.NEGRO else "#111111",
                    )

        jugadas = -(-len(partida.historial) // 2)
        self.etiqueta_estado.configure(
            text=f"   {partida.resumen()}   ·   {partida.estado.nombre_legible}"
                 f"   ·   Jugada {partida.numero_movimiento} ({jugadas} jugadas)"
        )

    def _pintar_coordenadas(
        self, x0: int, y0: int, fila: int, columna: int, oscuro: bool
    ) -> None:
        """Escribe el número de fila a la izquierda y la letra de columna abajo.

        Las dos hacen falta porque el programa entero se maneja por
        coordenadas ("e2-e4"): sin ellas no se puede leer ninguna.
        """
        color = CLARA if oscuro else OSCURA
        letra = "abcdefgh"[columna]
        self.lienzo.create_text(
            x0 + 4, y0 + 2, text=str(fila + 1), anchor="nw",
            fill=color, font=("Consolas", 8),
        )
        if fila == 0:
            # La primera fila es la de abajo en pantalla, así que su letra va
            # en el borde inferior de la casilla.
            self.lienzo.create_text(
                x0 + LADO_CASILLA / 2, y0 + LADO_CASILLA - 2, text=letra, anchor="s",
                fill=color, font=("Consolas", 9),
            )
        if fila == 7:
            self.lienzo.create_text(
                x0 + 4, y0 + LADO_CASILLA - 2, text=letra, anchor="sw",
                fill=color, font=("Consolas", 9),
            )

    def _fuente_de_piezas(self) -> tuple[str, int]:
        """Fuente de las piezas: la primera que tenga los símbolos de ajedrez.

        No todas las fuentes de Windows los incluyen, y sin una el tablero sale
        con cuadrados vacíos. Se prueban por orden y se usa la primera que
        exista; si ninguna, la del sistema, que al menos no da error.
        """
        disponibles = set(tkfont.families(self.root))
        for nombre in ("Segoe UI Symbol", "DejaVu Sans", "Noto Sans Symbols 2", "Arial Unicode MS"):
            if nombre in disponibles:
                return (nombre, 26)
        return ("TkDefaultFont", 24)

    # ------------------------------------------------------------------
    # Preguntar: los ocho métodos que sí esperan
    # ------------------------------------------------------------------
    # Son los únicos que bloquean, y por eso están juntos y con el motivo
    # escrito: son el punto exacto que habría que cambiar para tener una
    # ventana con botones de verdad en vez de con diálogos modales.

    def menu_inicio(self) -> str:
        return self._dialogo(
            "Ajedrez", "¿Qué quiere hacer?", opciones=self.OPCIONES_INICIO
        ) or "0"

    def menu_partida(self) -> str:
        return self._dialogo(
            "Partida en curso", "¿Qué quiere hacer?", opciones=self.OPCIONES_PARTIDA
        ) or "0"

    def menu_archivo(self) -> str:
        return self._dialogo(
            "Partidas guardadas", "¿Qué quiere hacer?", opciones=self.OPCIONES_ARCHIVO
        ) or "0"

    def elegir_color(self) -> Color:
        respuesta = self._dialogo(
            "Color",
            "Juegas con un solo color; el contrario lo juega otra persona.\n"
            "Las blancas mueven primero.",
            opciones={"1": "Blancas (mueven primero)", "2": "Negras"},
        )
        return Color.BLANCO if respuesta in ("1", None) else Color.NEGRO

    def pedir_confirmacion(self, pregunta: str) -> bool:
        return self._dialogo("Confirmar", pregunta, opciones={"1": "Sí", "0": "No"}) == "1"

    def pedir_jugada(self) -> str:
        return self._dialogo(
            "Jugada",
            "Escribe la jugada.\n(e2e4, e2-e4, o a7a8q para promover a dama)",
            por_defecto="",
        ) or ""

    def pedir_texto_opcional(self, pregunta: str) -> str | None:
        # Un campo vacío y "Cancelar" significan lo mismo: que no hay nombre.
        # Sin esta equivalencia, cancelar devolvería "" y el controlador
        # intentaría guardar una partida con la clave vacía.
        respuesta = self._dialogo("Escribir", pregunta)
        return respuesta or None

    def pedir_texto(self, pregunta: str, por_defecto: str = "") -> str:
        return self._dialogo("Escribir", pregunta, por_defecto=por_defecto) or por_defecto
