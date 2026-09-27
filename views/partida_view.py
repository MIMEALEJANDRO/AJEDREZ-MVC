"""Vista de consola: la única capa del programa que usa entrada y salida.

Por qué esta capa existe y las demás no: las reglas de ajedrez se pueden
probar y reutilizar, pero no se pueden probar si están mezcladas con la
impresión. Al dejar toda la entrada y la salida aquí, el resto del programa es
lógica pura y las pruebas pueden comprobarla sin necesidad de una terminal.

Para que la vista siga siendo comprobable, los dos flujos (entrada y salida)
se reciben en el constructor en vez de usar los globales. Por defecto son la
consola, así que desde el programa normal no se nota; en las pruebas se les
pasa un ``StringIO`` y se puede comprobar exactamente qué se imprime y qué se
responde.

La vista no contiene ninguna regla de ajedrez ni ningún detalle del formato
en que se guardan las partidas: solo traduce entre lo que la persona ve y
escribe, y los objetos del modelo.

La clase implementa ``views.interfaz.InterfazVista``, que es el contrato que
exige el controlador. Ese contrato vive en su propio archivo para que el
controlador no dependa de la consola: si mañana esta clase se sustituye por una
ventana, el controlador no se toca (mientras abide del contrato, que es
justamente lo que el Protocol comprueba).
"""

from __future__ import annotations

import sys
from typing import TextIO

from models.enums import Color, EstadoPartida
from models.partida import Partida
from views.interfaz import (
    OPCIONES_ARCHIVO,
    OPCIONES_INICIO,
    OPCIONES_PARTIDA,
    InterfazVista,
    texto_del_error,
)

# Ancho de las cabeceras de menú, para que el texto quede alineado.
ANCHO = 46


class PartidaView(InterfazVista):
    """Pinta el tablero y los menús, y recoge lo que la persona escribe.

    Las tres tablas de opciones se importan de ``views.interfaz`` y además se
    dejan accesibles como atributos de clase (``PartidaView.OPCIONES_INICIO``).
    Duplicarlas no aporta nada y convertirlas en atributos sí: es la forma
    barata de tener "las opciones de esta pantalla" a mano sin buscarlas en otro
    módulo.
    """

    OPCIONES_INICIO = OPCIONES_INICIO
    OPCIONES_PARTIDA = OPCIONES_PARTIDA
    OPCIONES_ARCHIVO = OPCIONES_ARCHIVO

    def __init__(self, entrada: TextIO | None = None, salida: TextIO | None = None) -> None:
        # ``None`` significa "la consola de verdad". Se resuelve una sola vez
        # aquí, en el constructor, en vez de en cada llamada, para que las
        # pruebas puedan inyectar sus propios flujos.
        self.entrada = entrada if entrada is not None else sys.stdin
        self.salida = salida if salida is not None else sys.stdout

    # ------------------------------------------------------------------
    # Salida: cómo se pinta
    # ------------------------------------------------------------------

    def escribir(self, texto: str = "") -> None:
        """Escribe una línea de texto."""
        print(texto, file=self.salida)

    def titulo(self, texto: str) -> None:
        """Escribe un separador con título, para separar secciones del menú.

        El número de guiones se calcula a partir del título para que todos los
        separadores midan lo mismo, como se ve al escribirlo a mano: si el
        texto es más largo que el hueco, ``max(0, ...)`` deja cero guiones en
        vez de pasarse de ancho.
        """
        self.escribir()
        self.escribir(f"--- {texto} " + "-" * max(0, ANCHO - len(texto) - 6))

    def mostrar_mensaje(self, mensaje: str) -> None:
        """Mensaje normal del programa."""
        self.escribir(mensaje)

    def mostrar_error(self, error: Exception | str) -> None:
        """Muestra un error de forma útil.

        Hay tres casos, y se distinguen porque cada uno merece un trato
        distinto:

        * Un ``ErrorAjedrez`` es siempre un problema con lo que escribió la
          persona, así que se muestra tal cual: ya viene redactado para eso.
        * Una cadena suelta es un mensaje redactado por el controlador (por
          ejemplo "no se pudo escribir en disco"). Se muestra tal cual, sin el
          adorno de "error inesperado", que haría pensar en un fallo del
          programa cuando no lo es.
        * Cualquier otra excepción es inesperada y se muestra su tipo, que es
          la información útil para saber qué está fallando. Esta vista no lanza
          nada: mostrar un error es justo lo que hace, y propagar la excepción
          es cosa del controlador, que es quien decide si se puede seguir.

        El texto en sí lo decide ``views.interfaz.texto_del_error`` y no esta
        vista, para que una ventana no tenga que decidirlo por su cuenta.
        """
        self.escribir(f"  {texto_del_error(error)}")

    # ------------------------------------------------------------------
    # Entrada: cómo se pregunta
    # ------------------------------------------------------------------

    def _pedir_linea(self) -> str | None:
        """Lee una línea de la entrada, o ``None`` si ya no queda ninguna.

        Se escribe el texto de interrupción directamente en el flujo de salida
        y se lee de la entrada, en vez de usar ``input()``, por dos razones:
        ``input()`` siempre trabaja con los flujos globales (y rompería la
        inyección de dependencias) y lanza ``EOFError`` al agotarse la entrada.

        Devolver ``None`` en vez de lanzar deja que cada pregunta decida qué
        hacer cuando no hay quien responda, en vez de repetir el mismo ``try``
        en todos los métodos.
        """
        linea = self.entrada.readline()
        if linea == "":
            # Se llegó al final de la entrada: pasa lo mismo que si alguien
            # pulsa Ctrl+Z. Es el final de la partida de la conversación, no un
            # error del programa.
            return None
        return linea.strip()

    def pedir_texto(self, pregunta: str, por_defecto: str = "") -> str:
        """Pide una línea de texto y devuelve lo escrito.

        ``por_defecto`` se muestra entre corchetes y se devuelve si se pulsa
        Enter sin escribir nada. Se acepta en mayúsculas y minúsculas porque
        en un menú pulsan Enter sin mirar.

        Devolver un valor vacío en vez de repreguntar en un bucle infinito es
        deliberado: deja que sea el llamante quien decida qué significa "no
        he escrito nada", en vez de esconder esa decisión aquí dentro.
        """
        return self._preguntar(pregunta, por_defecto)[0]

    def _preguntar(self, pregunta: str, por_defecto: str = "") -> tuple[str, bool]:
        """Escribe la pregunta y devuelve ``(respuesta, hubo_entrada)``.

        El segundo valor dice si alguien respondió de verdad o si la entrada
        se había agotado. Hace falta porque "no hay quien responda" y "ha
        pulsed Enter" dan la misma respuesta pero no pueden llevar a la misma
        decisión: quien repregunta en bucle ante la primera se cuelga, y quien
        la trata como la segunda entra en un bucle infinito por otro lado.
        """
        if por_defecto:
            pregunta = f"{pregunta} [{por_defecto}]"
        print(f"{pregunta}: ", end="", file=self.salida)
        self.salida.flush()
        respuesta = self._pedir_linea()
        if respuesta is None:
            return por_defecto, False
        return respuesta or por_defecto, True

    def pedir_opcion(
        self,
        opciones: dict[str, str],
        pregunta: str = "Seleccione una opción",
        al_agotar: str | None = None,
    ) -> str:
        """Muestra las opciones y devuelve la clave elegida.

        ``opciones`` es un diccionario ``{clave: texto}``, del tipo
        ``{"1": "Nueva partida", "0": "Salir"}``.

        Se compara con la clave exacta (``respuesta in opciones``) y no con el
        texto: comparar textos aceptaría "salir" para la opción "Salir a la
        partida" y otros falsos positivos molestos. Se repregunta en bucle
        porque elegir mal de un menú sí es un error de quien está usando el
        programa, y repreguntar es más amable que terminar.

        ``al_agotar`` es la clave que se devuelve cuando ya no queda entrada que
        leer (Ctrl+D, una entrada canalizada desde otro programa, o el final de
        un ``StringIO`` en las pruebas). Si no se indica se usa ``"0"``, que en
        todos los menús de este programa es "volver o salir". No es una
        preferencia: repreguntar en bucle dejaría el programa colgado para
        siempre, y devolver cualquier otra opción lo dejaría igual de colgado
        por otro camino (``pedir_jugada`` devolvería cadena vacía y el bucle de
        juego no avanzaría nunca). Terminar es la única respuesta honesta a
        "ya no hay nadie a quien preguntar".
        """
        if al_agotar is None:
            al_agotar = "0" if "0" in opciones else next(iter(opciones))
        for clave, texto in opciones.items():
            self.escribir(f"  {clave}. {texto}")
        while True:
            respuesta, hubo_entrada = self._preguntar(pregunta)
            if respuesta in opciones:
                return respuesta
            if not hubo_entrada:
                return al_agotar
            # Solo se avisa si hubo una entrada que no era válida. Si no la
            # hubo (final del archivo, Ctrl+D) ya se ha terminado arriba, y
            # avisar de una opción vacía sería confuso.
            self.escribir(f"  Opción no válida: {respuesta!r}. Las válidas son: "
                          f"{', '.join(opciones)}.")

    def pedir_confirmacion(self, pregunta: str) -> bool:
        """Pregunta sí o no.

        Se aceptan todas las formas habituales de decir que sí ("s", "si",
        "sí", "y", "yes", "1", "true"), en minúsculas y sin tildes, porque
        escribirlas con tilde en una consola antigua es una molestia. Cualquier
        otra cosa se interpreta como "no", que es la opción segura.
        """
        respuesta = self.pedir_texto(f"{pregunta} (s/N)").lower()
        return respuesta in ("s", "si", "sí", "y", "yes", "1", "true")

    def pedir_texto_opcional(self, pregunta: str) -> str | None:
        """Pide un texto admitiendo la opción de cancelar.

        Se usa donde "no hacer nada" es una respuesta legítima (no guardar, no
        renombrar). Devolver ``None`` en vez de una cadena vacía permite
        distinguir "se canceló" de "se aceptó un texto vacío", que son cosas
        distintas.
        """
        respuesta = self.pedir_texto(f"{pregunta} ('-' para cancelar)")
        if respuesta == "-":
            return None
        return respuesta or None

    # ------------------------------------------------------------------
    # Presentación de la partida
    # ------------------------------------------------------------------

    def mostrar_tablero(self, partida: Partida) -> None:
        """Pinta el tablero, el turno y el estado.

        La primera columna son los números de fila y la última las letras de
        columna, y las dos hacen falta: sin ellas no se puede leer ninguna
        coordenada, y la aplicación entera se maneja por coordenadas
        ("e2-e4"). El dibujo en sí lo hace el propio tablero con ``str()``,
        que es quien sabe cómo es una casilla.
        """
        self.titulo("Tablero")
        self.escribir(str(partida.tablero))
        self.escribir()
        self.escribir(f"  {partida.resumen()}")
        etiqueta = partida.estado.nombre_legible
        # El número de jugadas completas es la mitad del historial, redondeada
        # hacia arriba: tras 1 jugada hay medio juego, tras 2 hay 1 juego.
        jugadas = -(-len(partida.historial) // 2)
        self.escribir(f"  Estado: {etiqueta} | Jugada {partida.numero_movimiento} "
                      f"({jugadas} jugadas)")
        if partida.estado is not EstadoPartida.EN_CURSO:
            self.escribir(f"  Motivo: {partida.motivo}")

    def mostrar_fen(self, partida: Partida) -> None:
        """Pinta el FEN, que sirve para copiar la posición a otro programa."""
        self.titulo("Notación FEN")
        self.escribir(f"  {partida.a_fen()}")

    def mostrar_historial(self, partida: Partida) -> None:
        """Pinta las jugadas en notación ("1. e2-e4  e7-e5...")."""
        self.titulo("Historial")
        if not partida.historial:
            self.escribir("  (todavía no hay jugadas)")
            return
        for linea in partida.jugadas_en_notacion():
            self.escribir(f"  {linea}")

    def mostrar_ayuda(self) -> None:
        """Pinta el resumen de los menús, para no tener que recordarlos."""
        self.titulo("Ayuda")
        self.escribir("  - Una jugada se escribe con origen y destino pegados:")
        self.escribir("      e2e4, e2-e4 o 'e2 e4'.")
        self.escribir("  - Un peón que llega al final necesita promoción:")
        self.escribir("      a7a8q  (q = dama, r = torre, b = alfil, n = caballo).")
        self.escribir("  - Enroque: e1g1 con el rey y la torre en su sitio,")
        self.escribir("      y sin estar en jaque ni pasar por una casilla atacada.")
        self.escribir("  - Comandos: 'menu', 'historial', 'fen', 'ayuda', 'salir'.")
        self.escribir("  - Opción 3 del menú principal: guardar, cargar, listar o")
        self.escribir("      borrar las partidas ya guardadas.")

    # ------------------------------------------------------------------
    # Listas
    # ------------------------------------------------------------------

    def mostrar_partidas(self, informes: list[dict]) -> None:
        """Pinta la lista de partidas guardadas, con su identificador.

        El identificador se muestra siempre y no solo el nombre, porque es lo
        que hay que escribir en el siguiente paso para cargar o borrar. Si se
        enseñara únicamente el nombre, habría que adivinar el identificador
        después.
        """
        self.titulo("Partidas guardadas")
        if not informes:
            self.escribir("  (no hay ninguna partida guardada)")
            return
        for informe in informes:
            self.escribir(
                f"  {informe['id']}  {informe.get('fecha', ''):<20}"
                f"{informe.get('resultado', ''):<14}{informe.get('nombre', '')}"
            )

    # ------------------------------------------------------------------
    # Menús
    # ------------------------------------------------------------------
    # Las tablas de opciones están en ``views.interfaz`` y se han expuesto como
    # atributos de clase al principio del archivo. Aquí solo queda el trabajo de
    # pintarlas: un título y la pregunta.

    def menu_inicio(self) -> str:
        """Menú principal, antes de empezar a jugar."""
        self.titulo("Ajedrez")
        return self.pedir_opcion(self.OPCIONES_INICIO, "¿Qué quiere hacer?")

    def menu_partida(self) -> str:
        """Menú de la partida en curso."""
        self.titulo("Partida en curso")
        return self.pedir_opcion(self.OPCIONES_PARTIDA, "¿Qué quiere hacer?")

    def menu_archivo(self) -> str:
        """Menú de gestión de partidas guardadas."""
        self.titulo("Partidas guardadas")
        return self.pedir_opcion(self.OPCIONES_ARCHIVO, "¿Qué quiere hacer?")

    def elegir_color(self) -> Color:
        """Pregunta con qué color se juega.

        Se juega con un solo color: el otro lo juega quien esté al otro lado
        (o quien abra el programa en otra ventana). Es la opción adecuada para
        un ejercicio de reglas: no hay un rival automático, hay una persona.

        No se comparan aquí las respuestas con "1" y "2" a mano: eso es
        ``Color.desde_texto``, que ya acepta el número, el nombre y la inicial,
        y que está probado. Preguntar con la tabla de la vista y traducir con la
        del modelo son dos listas que se desincronizarían en cuanto se añadiera
        una forma nueva de escribir el color.

        Si la entrada se agota se juega con las blancas, que es lo que
        corresponde al valor por defecto del menú.
        """
        self.titulo("Color")
        self.escribir("  Juegas con un solo color; el contrario lo juega la persona")
        self.escribir("  al otro lado de la mesa (o en otra ventana del programa).")
        self.escribir("  1. Blancas (mueven primero)")
        self.escribir("  2. Negras")
        while True:
            respuesta = self.pedir_texto("Color con el que juegas", "1")
            try:
                return Color.desde_texto(respuesta)
            except ValueError:
                self.escribir("  Opción no válida. Elija 1 o 2.")

    def pedir_jugada(self) -> str:
        """Pide la jugada con un solo texto libre.

        No se pide el origen con una llamada a ``pedir_texto`` y el destino con
        otra a propósito: quien está pensando una jugada preferiría escribirla
        de una vez ("e2e4"), y el programa la puede partir sin problema. Así una
        jugada son cuatro teclas y no cuatro más un Enter de por medio.
        """
        return self.pedir_texto("Jugada")
