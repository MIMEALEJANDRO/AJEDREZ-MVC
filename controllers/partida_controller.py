"""Controlador: el que coordina modelo, vista y almacenamiento.

Es la capa que "entiende" lo que la persona ha pedido y decide a quién le toca
resolverlo. Su trabajo se puede resumir en tres frases:

1. **Hablar con la persona** (a través de la vista) para saber qué quiere.
2. **Traducir** lo que ha escrito a objetos del modelo: "e2e4q" a
   ``Posicion``, ``Posicion``, ``TipoPieza``.
3. **Decidir qué pintar** con lo que devuelve el modelo.

El controlador no decide *qué jugada es legal*: eso es del modelo. Y no
escribe en pantalla: eso es de la vista. Su valor está en que conoce a las
tres capas y no depende de ninguna en concreto:

* recibe la ``Partida``, una ``InterfazVista`` y el ``BaseStorage`` en el
  constructor, así que se puede probar con dobles sin tocar el disco ni la
  pantalla;
* cambiar de JSON a FEN es cambiar un argumento, no reescribir el controlador;
* cambiar de consola a ventana es cambiar un argumento, porque solo conoce el
  contrato de la vista y no ninguna vista en concreto.

Los errores del dominio no se capturan aquí para silenciarlos: se capturan
para *traducirlos*. ``MovimientoIlegal`` se convierte en un mensaje que
explica qué jugadas sí eran posibles, que es información que la persona
necesita y que el modelo no tiene por qué redactar.
"""

from __future__ import annotations

from models.enums import Color, EstadoPartida, TipoPieza
from models.errores import (
    ErrorAjedrez,
    MovimientoIlegal,
    PartidaNoEncontrada,
    PartidaTerminada,
)
from models.partida import Partida
from models.pieza import LETRAS_PROMOCION
from models.posicion import Movimiento, Posicion
from storage.base_storage import BaseStorage
from views.interfaz import InterfazVista

# Caracteres que se quitan del texto de una jugada antes de interpretarlo.
# Se admiten todos: "e2-e4", "e2e4", "e2 e4", "  e2e4  " y "e2:E4" son la
# misma jugada, y quien escribe en una consola con prisa no está para contar
# separadores.
SEPARADORES = "- \t:;,/"

# Prefijos de los comandos que se pueden escribir en vez de una jugada. Se
# eligen palabras que no pueden confundirse con una casilla (que son siempre
# letra+dígito), así que "fin" nunca podría ser un movimiento.
COMANDOS = {
    "menu": "menu",
    "m": "menu",
    "historial": "historial",
    "h": "historial",
    "fen": "fen",
    "f": "fen",
    "ayuda": "ayuda",
    "a": "ayuda",
    "?": "ayuda",
    "salir": "salir",
    "s": "salir",
    "q": "salir",
    "guardar": "guardar",
    "g": "guardar",
    "deshacer": "deshacer",
    "d": "deshacer",
    "tablas": "tablas",
}

# Formas en que se puede escribir la promoción, de la más larga a la más
# corta. Se ordena una sola vez al importar el módulo (y no en cada jugada)
# porque el orden es lo único que importa al buscar: si se buscara "c" antes
# que "caballo", "a7a8caballo" se quedaría en "a7a8cabal".
FORMAS_DE_PROMOCION = sorted(LETRAS_PROMOCION, key=len, reverse=True)


class PartidaController:
    """Coordina la partida en curso, la vista y el almacenamiento."""

    def __init__(
        self,
        vista: InterfazVista,
        partida: Partida | None = None,
        storage: BaseStorage | None = None,
        color_jugador: Color | None = None,
    ) -> None:
        # ``vista`` va primero y es obligatorio. Antes era opcional con un
        # ``PartidaView()`` por defecto, que tenía dos fallos: obligaba al
        # controlador a importar la consola (y con ella a depender de ella), y
        # escondía el error de "se me olvidó pasar la vista" hasta que el
        # controlador intentaba hablar con un ``None``.
        #
        # Los otros colaboradores sí son opcionales, porque tenerlos por
        # defecto es cómodo: la inyección por el constructor es lo que permite
        # guardar en una carpeta temporal o usar un doble de vista en las
        # pruebas sin tocar el resto del código.
        self.vista = vista
        self.partida = partida if partida is not None else Partida()
        self.storage = storage
        # Color con el que juega la persona. ``None`` significa "los dos
        # colores", que es lo que se usa en las pruebas y en el modo en que dos
        # personas comparten el mismo teclado.
        self.color_jugador = color_jugador
        # Última clave con la que se guardó esta partida. Sirve para que el
        # menú de guardado sepa si está creando una entrada nueva o
        # reemplazando una existente, y para poder volver a guardar sin que
        # se acumulen copias de la misma partida.
        self.clave_guardada: str | None = None

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def ejecutar(self) -> None:
        """Menú principal: nueva partida, gestionar archivos, ayuda o salir.

        Se elige el bucle más externo aquí y no en ``main.py`` a propósito:
        ``main.py`` solo configura (dónde se guarda, qué vista se usa) y
        ``controlador.ejecutar()`` es quien decide la forma de la conversación.
        Así la aplicación se puede probar entera desde aquí.
        """
        while True:
            opcion = self.vista.menu_inicio()
            if opcion == "0":
                self.vista.mostrar_mensaje("Hasta la próxima.")
                return
            if opcion == "1":
                self.jugar()
            elif opcion == "2":
                if not self.cargar():
                    self.vista.mostrar_mensaje("No se cargó ninguna partida.")
                else:
                    # Cargar no basta: la partida cargada no se muestra hasta
                    # que se elige jugar, y entre una cosa y otra quien la
                    # cargó se queda sin ver lo que ha cargado.
                    self.jugar()
            elif opcion == "3":
                self.gestionar_archivos()
            elif opcion == "4":
                self.vista.mostrar_ayuda()

    def gestionar_archivos(self) -> None:
        """Menú de gestión de las partidas guardadas.

        Existe como método aparte (y no en línea dentro de ``ejecutar``) porque
        es un bucle completo: listar, cargar y borrar son tres caminos que
        dependen del menú de archivos, y metidos en ``ejecutar`` lo dejarían
        reducido a un ``if`` de veinte líneas.

        Cargar desde aquí sí empieza a jugar: cargar sin llegar a ver el
        tablero dejaría a quien lo hizo sin saber qué ha cargado, que es el
        mismo motivo por el que ``ejecutar`` entra en ``jugar``.
        """
        while True:
            opcion = self.vista.menu_archivo()
            if opcion == "1":
                self.guardar()
            elif opcion == "2":
                if self.cargar():
                    self.jugar()
                    return
            elif opcion == "3":
                self.vista.mostrar_partidas(self.listar_guardadas())
            elif opcion == "4":
                self.eliminar_guardada()
            elif opcion == "0":
                return

    def jugar(self) -> None:
        """Bucle de la partida en curso.

        El bucle termina cuando la partida se acaba (mate, ahogado, tablas,
        abandono) o cuando la persona elige salir. Al terminar siempre se
        ofrece guardar, porque es justo en ese momento cuando la partida vale
        como registro.
        """
        # Si ya venía una partida cargada del menú principal, se sigue con ella
        # en vez de empezar otra desde cero.
        if not self.partida.historial and self.partida.estado is EstadoPartida.EN_CURSO:
            self.color_jugador = self.vista.elegir_color()

        while True:
            self.vista.mostrar_tablero(self.partida)
            # Una partida ya terminada se muestra una vez más y se sale del
            # bucle: no tiene sentido ofrecer el menú de jugar.
            if self.partida.esta_terminada():
                self.vista.mostrar_mensaje(f"  La partida terminó: {self.partida.motivo}.")
                if self.storage is not None:
                    self.ofrecer_guardado()
                return

            opcion = self.vista.menu_partida()
            if opcion == "1":
                self.introducir_jugada()
            elif opcion == "2":
                self.vista.mostrar_historial(self.partida)
            elif opcion == "3":
                self.vista.mostrar_fen(self.partida)
            elif opcion == "4":
                self.deshacer()
            elif opcion == "5":
                self.guardar()
            elif opcion == "6":
                # Solo se empieza la partida nueva si el guardado se hizo de
                # verdad. ``guardar`` devuelve la clave con la que quedó, o
                # ``None`` si no había almacenamiento, si se canceló el nombre
                # o si falló el disco. Reiniciar igualmente en ese caso
                # borraría la partida en memoria sin guardarla en ninguna parte:
                # se perdería sin dejar rastro, que es la peor forma de perderla.
                if self.guardar():
                    self.nueva_partida()
                else:
                    self.vista.mostrar_mensaje(
                        "  No se ha empezado otra partida: la actual sigue aquí."
                    )
            elif opcion == "7":
                self.abandonar()
            elif opcion == "8":
                self.vista.mostrar_ayuda()
            elif opcion == "0":
                # Volver al menú principal **sin** ofrecer guardar: la partida
                # sigue en memoria y se puede volver a ella con "continuar una
                # partida guardada" (si se guardó) o con "partida nueva". Si no
                # se guardó, el programa lo recuerda al reiniciar, porque la
                # partida sigue siendo el mismo objeto.
                self.vista.mostrar_mensaje("  Se vuelve al menú principal.")
                return

    def nueva_partida(self) -> None:
        """Empieza una partida nueva desde la posición inicial."""
        self.partida.reiniciar()
        # Se olvida la clave guardada: es otra partida y no debe reemplazar a
        # la anterior en el almacenamiento.
        self.clave_guardada = None
        self.color_jugador = self.vista.elegir_color()

    # ------------------------------------------------------------------
    # Jugadas
    # ------------------------------------------------------------------

    def introducir_jugada(self) -> None:
        """Pide una jugada por texto, la interpreta y la intenta aplicar.

        Devuelve ``True`` si la jugada se aceptó. Ese valor lo usan las
        pruebas para comprobar el resultado sin mirar lo impreso, y no tiene
        otro uso en el programa: el bucle vuelve a pintar el tablero igual.
        """
        texto = self.vista.pedir_jugada()
        if not texto:
            return False

        # 1) ¿Es un comando del menú? Entonces no es una jugada.
        comando = COMANDOS.get(texto.strip().lower())
        if comando is not None:
            self._ejecutar_comando(comando)
            return False

        # 2) Traducir el texto a un movimiento del modelo.
        try:
            movimiento, promocion = self.parsear_jugada(texto)
        except ErrorAjedrez as error:
            self.vista.mostrar_error(error)
            return False

        # 3) Comprobar a quién le toca mover. Esta comprobación es del
        #    controlador y no del modelo porque es una regla de *la
        #    aplicación*, no de ajedrez: el modelo permite jugar con el color
        #    que sea, la aplicación es la que decide qué color usa la persona.
        if self.color_jugador is not None and self.partida.turno is not self.color_jugador:
            self.vista.mostrar_error(
                f"No es su turno: mueven las {self.partida.turno.value}s "
                f"y usted juega con las {self.color_jugador.value}s."
            )
            return False

        # 4) Aplicar la jugada. Los errores del modelo se traducen aquí.
        try:
            self.partida.mover(movimiento.origen, movimiento.destino, promocion)
        except (MovimientoIlegal, PartidaTerminada) as error:
            self.vista.mostrar_error(error)
            self._sugerir_ayuda(movimiento)
            return False

        # 5) Aviso de que la partida ha terminado: el bucle lo detecta en la
        #    vuelta siguiente, pero avisar aquí es más claro.
        if self.partida.esta_terminada():
            self.vista.mostrar_mensaje(f"  ¡{self.partida.motivo}!")
        return True

    def parsear_jugada(self, texto: str) -> tuple[Movimiento, TipoPieza | None]:
        """Convierte lo que escribió la persona en un movimiento y una promoción.

        Formatos aceptados, todos equivalentes::

            e2e4        e2-e4        e2 e4        e2:E4
            a7a8q       a7-a8=dama    a7a8d

        Devuelve ``(movimiento, promocion)``, donde ``promocion`` es ``None``
        si la jugada no promociona.

        Lanza ``ErrorAjedrez`` (o ``MovimientoIlegal``, que es subclase) con un
        mensaje pensado para leerse en pantalla, porque este es el punto donde
        se equivocan las manos y no el programa.
        """
        limpio = texto.strip().lower()
        for separador in SEPARADORES:
            limpio = limpio.replace(separador, "")
        if not limpio:
            raise MovimientoIlegal("No se ha escrito ninguna jugada.")

        # Se separa la promoción si la hay. Solo puede ir al final, y se
        # buscan las formas **de la más larga a la más corta** ("caballo"
        # antes que "c"): si se buscara la letra primero, "a7a8dama" se
        # quedaría con "a7a8dam" y no se reconocería.
        #
        # Solo tiene sentido mirarlo si sobra algo: "e2e4" mide cuatro
        # caracteres y su última letra es un "4", que no puede ser una
        # promoción. Sin esa condición, "a7a8b" perdería la "b" del alfil y se
        # quedaría sin destino.
        promocion: TipoPieza | None = None
        if len(limpio) > 4:
            for sufijo in FORMAS_DE_PROMOCION:
                if len(sufijo) < len(limpio) and limpio.endswith(sufijo):
                    promocion = LETRAS_PROMOCION[sufijo]
                    limpio = limpio[: -len(sufijo)]
                    break

        if len(limpio) != 4:
            raise MovimientoIlegal(
                f"Jugada no reconocida: {texto!r}. Use el formato origen-destino, por ejemplo 'e2e4'."
            )
        try:
            origen = Posicion.desde_notacion(limpio[:2])
            destino = Posicion.desde_notacion(limpio[2:])
        except ErrorAjedrez as error:
            raise MovimientoIlegal(
                f"Casillas no válidas en {texto!r}. Use columnas a-h y filas 1-8, por ejemplo 'e2e4'."
            ) from error
        return Movimiento(origen, destino), promocion

    def _ejecutar_comando(self, comando: str) -> None:
        """Atiende los comandos que se pueden escribir en el hueco de una jugada.

        Se toleran porque la gente los escribe sin pensarlo: es mucho más
        natural escribir "ayuda" o "fen" en el prompt de la jugada que buscar
        la opción en un menú. El coste es cero y el beneficio real.
        """
        if comando == "menu":
            self.vista.mostrar_mensaje("  (use el menú para elegir una opción).")
        elif comando == "historial":
            self.vista.mostrar_historial(self.partida)
        elif comando == "fen":
            self.vista.mostrar_fen(self.partida)
        elif comando == "ayuda":
            self.vista.mostrar_ayuda()
        elif comando == "guardar":
            self.guardar()
        elif comando == "deshacer":
            self.deshacer()
        elif comando == "tablas":
            self.empatar()
        elif comando == "salir":
            # "salir" en el prompt de una jugada no cierra el programa (eso
            # sería peligroso por un despiste), solo cancela la entrada: se
            # vuelve al menú de la partida.
            self.vista.mostrar_mensaje(
                "  (continúa la partida; para salir del todo, elige la opción 0)."
            )

    def _sugerir_ayuda(self, movimiento: Movimiento) -> None:
        """Tras una jugada ilegal, muestra qué se podía hacer desde esa casilla.

        Es la diferencia entre "no se puede" y "desde e2 solo podías ir a e3
        o e4". La lista la calcula el modelo y el controlador decide si merece
        la pena enseñarla: solo si la casilla tiene alguna pieza y al menos un
        movimiento legal.
        """
        if not self.partida.tablero.en_juego(movimiento.origen):
            self.vista.mostrar_mensaje(f"  No hay ninguna pieza en {movimiento.origen.notacion}.")
            return
        legales = self.partida.tablero.movimientos_de(movimiento.origen)
        if not legales:
            self.vista.mostrar_mensaje(
                f"  La pieza de {movimiento.origen.notacion} no puede moverse: "
                "pondría en jaque a su propio rey."
            )
            return
        destinos = ", ".join(jugada.destino.notacion for jugada in legales)
        self.vista.mostrar_mensaje(f"  Desde {movimiento.origen.notacion} se puede ir a: {destinos}.")

    def deshacer(self) -> bool:
        """Deshace la última jugada, si la hay."""
        deshecho = self.partida.deshacer()
        if deshecho is None:
            self.vista.mostrar_mensaje("  No hay jugadas que deshacer.")
            return False
        self.vista.mostrar_mensaje(f"  Jugada deshecha: {deshecho.notacion}.")
        return True

    def abandonar(self) -> None:
        """Abandona la partida, previa confirmación.

        Abandonar es la única acción de la aplicación que no tiene vuelta
        atrás en el sentido de que la partida se marca como terminada para
        siempre, así que pide confirmación. Es una decisión de la aplicación,
        no una regla del juego, por eso está en el controlador y no en el
        modelo.
        """
        if not self.vista.pedir_confirmacion("¿Seguro que quiere abandonar la partida?"):
            return
        try:
            self.partida.abandonar()
        except PartidaTerminada as error:
            self.vista.mostrar_error(error)

    def empatar(self) -> None:
        """Declara tablas de mutuo acuerdo, previa confirmación.

        Las tablas por acuerdo solo existen porque alguien las pide: ningún
        motor de reglas puede deducirlas de la posición. Es un caso similar al
        abandono, y por eso también vive en el controlador.
        """
        if not self.vista.pedir_confirmacion("¿Seguro que quiere declarar tablas?"):
            return
        if self.partida.esta_terminada():
            self.vista.mostrar_error("La partida ya terminó.")
            return
        self.partida.estado = EstadoPartida.TABLAS
        self.partida.ganador = None
        self.partida.motivo = "Acuerdo de tablas"
        self.vista.mostrar_mensaje("  Tablas por mutuo acuerdo.")

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def guardar(self, nombre: str | None = None) -> str | None:
        """Guarda la partida en el almacenamiento. Devuelve la clave, o ``None``.

        Si la partida ya estaba guardada se vuelve a usar su clave, de modo que
        guardar dos veces la misma partida la actualiza en lugar de crear una
        copia nueva. Es lo que espera cualquiera que juegue, pratique y vuelva
        a guardar.
        """
        if self.storage is None:
            self.vista.mostrar_error("No hay almacenamiento configurado.")
            return None
        if nombre is None:
            nombre = self.vista.pedir_texto_opcional("Nombre de la partida")
            if nombre is None:
                self.vista.mostrar_mensaje("  Guardado cancelado.")
                return None
        clave = self.clave_guardada
        if clave is not None and not self.storage.existe(clave):
            # El archivo pudo borrarse entre guardado y guardado. Si ya no
            # está, se crea una clave nueva en vez de fallar.
            clave = None
        try:
            clave = self.storage.guardar(self.partida, nombre, clave)
        except OSError as error:
            # Los errores de disco (permiso, carpeta llena) no son errores del
            # dominio: se capturan aquí y se traducen a un mensaje, para que
            # el programa no se caiga con una traza de error.
            self.vista.mostrar_error(f"no se pudo escribir en disco ({error})")
            return None
        self.clave_guardada = clave
        self.vista.mostrar_mensaje(f"  Partida guardada con la clave {clave}.")
        return clave

    def cargar(self, clave: str | None = None) -> bool:
        """Carga una partida guardada y se convierte en la partida en curso."""
        if self.storage is None:
            self.vista.mostrar_error("No hay almacenamiento configurado.")
            return False
        if clave is None:
            self.vista.mostrar_partidas(self.storage.listar_informes())
            clave = self.vista.pedir_texto_opcional("Clave de la partida a cargar")
            if clave is None:
                return False
        try:
            partida = self.storage.cargar(clave)
        except PartidaNoEncontrada as error:
            self.vista.mostrar_error(error)
            return False
        except (OSError, ValueError) as error:
            # Un JSON con datos inválidos lanza ValueError al rehidratar los
            # enums; un archivo ilegible lanza OSError. Los dos son "el
            # archivo está dañado" para quien está usando el programa.
            self.vista.mostrar_error(f"el archivo de la partida no se pudo leer ({error})")
            return False
        self.partida = partida
        self.clave_guardada = clave
        self.vista.mostrar_mensaje(f"  Partida {clave} cargada.")
        return True

    def listar_guardadas(self) -> list[dict]:
        """Devuelve los informes de las partidas guardadas.

        Los errores de disco se convierten en una lista vacía en vez de
        propagarse: no poder leer el disco no debería impedir jugar, y el
        mensaje de error ya está mostrado.
        """
        if self.storage is None:
            return []
        try:
            return self.storage.listar_informes()
        except (OSError, PartidaNoEncontrada) as error:
            self.vista.mostrar_error(error)
            return []

    def eliminar_guardada(self, clave: str | None = None) -> bool:
        """Borra una partida guardada, previa confirmación."""
        if self.storage is None:
            self.vista.mostrar_error("No hay almacenamiento configurado.")
            return False
        if clave is None:
            self.vista.mostrar_partidas(self.listar_guardadas())
            clave = self.vista.pedir_texto_opcional("Clave de la partida a borrar")
            if clave is None:
                return False
        if not self.vista.pedir_confirmacion(f"¿Borrar la partida {clave}?"):
            return False
        try:
            borrada = self.storage.eliminar(clave)
        except OSError as error:
            self.vista.mostrar_error(f"no se pudo borrar el archivo ({error})")
            return False
        if not borrada:
            self.vista.mostrar_mensaje(f"  No existía ninguna partida con la clave {clave}.")
            return False
        # Si se borró la partida que se está jugando, se olvida su clave: si
        # no, el siguiente guardado intentaría reemplazar algo que ya no está.
        if clave == self.clave_guardada:
            self.clave_guardada = None
        self.vista.mostrar_mensaje(f"  Partida {clave} borrada.")
        return True

    def ofrecer_guardado(self) -> str | None:
        """Al terminar la partida, ofrece guardarla.

        Devuelve la clave con la que quedó guardada, o ``None`` si la persona
        no quiso guardarla. Es un método aparte porque se llama desde dos sitios
        (al terminar una partida y al salir del programa) y no merece la pena
        duplicar el texto de la pregunta.
        """
        self.vista.mostrar_mensaje("\n  ¿Quiere guardar esta partida para seguir más adelante?")
        if not self.vista.pedir_confirmacion("Guardar la partida"):
            return None
        return self.guardar()
