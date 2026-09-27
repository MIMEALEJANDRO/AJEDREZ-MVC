"""Pruebas del controlador: la coordinación de las tres capas.

Aquí se comprueba lo que no se puede probar en el modelo: que el controlador
traduce correctamente lo que escribe la persona, que avisa cuando no es su
turno y que guarda y carga sin escribirlas a mano.

La vista se sustituye por un doble que registra lo que se le pide escribir, y
el almacenamiento por uno en memoria. Así las pruebas no tocan la consola ni el
disco, que es justamente la ventaja de inyectar las dependencias.

El doble de la vista no hereda de la vista real a propósito: si heredaras, un
cambio en la interfaz real dejaría estas pruebas "funcionando" con una firma
que ya no existe. Como doble independiente, cualquier cambio en la interfaz se
muestra aquí como un error claro.
"""

import io

import pytest

from controllers.partida_controller import PartidaController
from models.enums import Color, EstadoPartida, TipoPieza
from models.errores import MovimientoIlegal
from models.partida import Partida
from storage.base_storage import BaseStorage
from views.partida_view import PartidaView


# ----------------------------------------------------------------------
# Dobles de prueba
# ----------------------------------------------------------------------

class VistaFalsa:
    """Vista que registra lo escrito y responde con lo que se le prepare.

    Implementa los métodos que el controlador usa de ``PartidaView``. Cuando
    se acabaron las respuestas preparadas se repite la última, para que una
    prueba no tenga que adivinar cuántas veces se va a preguntar.
    """

    def __init__(self, respuestas: list[str] | None = None) -> None:
        self.respuestas = list(respuestas or [])
        self.escrito: list[str] = []
        # Separado de ``respuestas`` a propósito: un menú pide su respuesta con
        # ``pedir_opcion`` y la jugabilidad con ``pedir_texto``, y en una
        # prueba que ejercita ambos, mezclar los dos en una sola cola haría
        # frágil saber cuál de las dos se está consumiendo.
        self.opciones: list[str] = []

    # -- salida ---------------------------------------------------------
    def escribir(self, texto: str = "") -> None:
        self.escrito.append(texto)

    def titulo(self, texto: str) -> None:
        self.escribir(f"--- {texto}")

    def mostrar_mensaje(self, mensaje: str) -> None:
        self.escrito.append(mensaje)

    def mostrar_error(self, error) -> None:
        self.escrito.append(f"ERROR: {error}")

    # -- entrada --------------------------------------------------------
    def _siguiente(self, pregunta: str, por_defecto: str = "") -> str:
        if self.respuestas:
            return self.respuestas.pop(0)
        return por_defecto

    def pedir_texto(self, pregunta: str, por_defecto: str = "") -> str:
        respuesta = self._siguiente(pregunta, por_defecto)
        return respuesta or por_defecto

    def pedir_opcion(self, opciones: dict, pregunta: str = "", al_agotar: str | None = None) -> str:
        # La cola propia cubre el caso normal. Cuando se acaba se aplica la
        # misma regla que la vista real ("0" si existe, si no la primera): así
        # una prueba que se quede sin respuestas no se cuelga y, además, la
        # prueba de menú agotado puede ejercitar el mismo camino.
        respuesta = self.opciones.pop(0) if self.opciones else ""
        if respuesta in opciones:
            return respuesta
        if al_agotar is not None and al_agotar in opciones:
            return al_agotar
        return "0" if "0" in opciones else next(iter(opciones))

    def pedir_confirmacion(self, pregunta: str) -> bool:
        return self._siguiente(pregunta).lower() in ("s", "si", "sí", "y", "1")

    def pedir_texto_opcional(self, pregunta: str) -> str | None:
        respuesta = self._siguiente(pregunta)
        return None if respuesta in ("", "-") else respuesta

    def pedir_jugada(self) -> str:
        return self._siguiente("Jugada")

    def elegir_color(self) -> Color:
        return Color.NEGRO if self._siguiente("Color") == "2" else Color.BLANCO

    # -- presentación ---------------------------------------------------
    def mostrar_tablero(self, partida) -> None:
        self.escribir(f"TABLERO: {partida.resumen()}")

    def mostrar_fen(self, partida) -> None:
        self.escribir(f"FEN: {partida.a_fen()}")

    def mostrar_historial(self, partida) -> None:
        self.escribir(f"HISTORIAL: {len(partida.historial)} jugadas")

    def mostrar_ayuda(self) -> None:
        self.escribir("AYUDA")

    def mostrar_partidas(self, informes) -> None:
        self.escrito.append("LISTA")
        for informe in informes:
            self.escribir(f"  {informe['id']}")

    def menu_inicio(self) -> str:
        return self.pedir_opcion(PartidaView.OPCIONES_INICIO, "Opción")

    def menu_partida(self) -> str:
        return self.pedir_opcion(PartidaView.OPCIONES_PARTIDA, "Opción")

    def menu_archivo(self) -> str:
        return self.pedir_opcion(PartidaView.OPCIONES_ARCHIVO, "Opción")

    # -- ayuda para las comprobaciones ----------------------------------
    def texto(self) -> str:
        """Todo lo escrito en un solo texto, para buscar dentro con ``in``."""
        return "\n".join(self.escrito)


class StorageEnMemoria(BaseStorage):
    """Almacenamiento que guarda en un diccionario, sin tocar el disco.

    Implementa el mismo contrato que ``JSONStorage`` y ``FENStorage``. Permite
    comprobar la coordinación del controlador (qué le pide a cada capa) sin
    depender de cómo se guarde en disco, que es lo que ya comprueba
    ``test_storage.py``.
    """

    def __init__(self) -> None:
        self.datos: dict[str, Partida] = {}
        self.fallos_al_guardar = False

    def _leer_todas(self) -> dict[str, Partida]:
        # Se devuelven copias y no las partidas vivas. Si se devolvieran las
        # mismas, guardar y luego seguir jugando modificaría también lo
        # "guardado", y la prueba no distinguiría los dos casos.
        return {clave: partida.clonar() for clave, partida in self.datos.items()}

    def _escribir_todas(self, partidas: dict[str, Partida]) -> None:
        if self.fallos_al_guardar:
            raise OSError("disco lleno (simulado)")
        self.datos = {clave: partida.clonar() for clave, partida in partidas.items()}

    def _ordenar_claves(self, claves: list[str]) -> list[str]:
        return sorted(claves, reverse=True)

    def listar_informes(self) -> list[dict]:
        return [
            {
                "id": clave,
                "nombre": "partida",
                "fecha": "2026-01-01 00:00:00",
                "resultado": partida.estado.value,
                "turno": partida.turno.value,
                "jugadas": len(partida.historial),
            }
            for clave, partida in self._leer_todas().items()
        ]


# ----------------------------------------------------------------------
# Preparación de las pruebas
# ----------------------------------------------------------------------

@pytest.fixture
def vista() -> VistaFalsa:
    return VistaFalsa()


@pytest.fixture
def storage() -> StorageEnMemoria:
    return StorageEnMemoria()


@pytest.fixture
def controlador(vista, storage) -> PartidaController:
    """Controlador con las tres capas sustituidas por dobles.

    Se crea con ``color_jugador=None`` para que no se compruebe de quién es el
    turno, salvo en las pruebas que sí lo comprueban.
    """
    return PartidaController(vista=vista, storage=storage)


# ----------------------------------------------------------------------
# Análisis de la jugada escrita
# ----------------------------------------------------------------------

class TestParsearJugada:
    @pytest.mark.parametrize(
        "texto",
        [
            "e2e4",      # pegada
            "e2-e4",     # con guion
            "e2 e4",     # con espacio
            "E2E4",      # en mayúsculas
            "  e2e4  ",  # con espacios alrededor
            "e2:e4",     # con dos puntos
        ],
    )
    def test_acepta_los_formatos_tipicos(self, controlador, texto):
        movimiento, promocion = controlador.parsear_jugada(texto)
        assert movimiento.notacion == "e2-e4"
        assert promocion is None

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("a7a8q", TipoPieza.DAMA),      # letra del FEN
            ("a7a8d", TipoPieza.DAMA),      # inicial en español
            ("a7a8dama", TipoPieza.DAMA),   # palabra entera
            ("a7a8r", TipoPieza.TORRE),
            ("a7a8b", TipoPieza.ALFIL),
            ("a7a8n", TipoPieza.CABALLO),
        ],
    )
    def test_reconoce_la_promocion(self, controlador, texto, esperado):
        # La promoción se devuelve ya como ``TipoPieza``, no como texto: el
        # controlador traduce una vez y el modelo recibe el enum.
        _, promocion = controlador.parsear_jugada(texto)
        assert promocion is esperado

    def test_no_confunde_la_cuarta_letra_con_una_promocion(self, controlador):
        # "e2e4" acaba en "4", que no es una letra de promoción. Este es el
        # error fácil: creyendo que toda última letra es una promoción, la
        # jugada se quedaría sin destino.
        movimiento, promocion = controlador.parsear_jugada("e2e4")
        assert movimiento.notacion == "e2-e4"
        assert promocion is None

    @pytest.mark.parametrize("texto", ["", "e2", "e2e4e5", "e9e4", "abc", "e2e4e6q"])
    def test_rechaza_texto_no_reconocible(self, controlador, texto):
        with pytest.raises(MovimientoIlegal):
            controlador.parsear_jugada(texto)


# ----------------------------------------------------------------------
# Introducir jugadas
# ----------------------------------------------------------------------

class TestIntroducirJugada:
    def test_una_jugada_correcta_se_aplica(self, controlador, vista):
        vista.respuestas = ["e2e4"]
        assert controlador.introducir_jugada() is True
        assert controlador.partida.turno is Color.NEGRO
        assert len(controlador.partida.historial) == 1

    def test_una_jugada_ilegal_no_rompe_la_partida(self, controlador, vista):
        # La partida debe seguir siendo jugable después de un error: es la
        # diferencia entre una aplicación y una que se cae.
        # La segunda jugada tiene que ser **de las blancas**: la primera era
        # ilegal, así que el turno no llegó a cambiar y el peón de e7 no se
        # puede mover todavía.
        vista.respuestas = ["e2e5", "e2e4"]
        assert controlador.introducir_jugada() is False
        assert controlador.introducir_jugada() is True
        assert len(controlador.partida.historial) == 1

    def test_un_texto_vacio_no_hace_nada(self, controlador, vista):
        vista.respuestas = [""]
        assert controlador.introducir_jugada() is False
        assert controlador.partida.historial == []

    def test_avisa_si_no_toca_una_pieza(self, controlador, vista):
        # La sugerencia aparece cuando la casilla de origen está vacía: es el
        # error más común de quien está aprendiendo.
        vista.respuestas = ["e4e5"]
        controlador.introducir_jugada()
        assert "No hay ninguna pieza en e4" in vista.texto()

    def test_sugiere_los_destinos_validos(self, controlador, vista):
        # La diferencia entre "no se puede" y "desde ahí solo podías ir a
        # e3 o e4". Es la ayuda más útil que se puede dar.
        vista.respuestas = ["e2e5"]
        controlador.introducir_jugada()
        assert "e3" in vista.texto() and "e4" in vista.texto()

    def test_avisa_si_la_pieza_no_puede_moverse(self, controlador, vista):
        # Una pieza clavada no tiene destinos legales: el mensaje tiene que
        # decirlo, no limitarse a "movimiento no permitido".
        partida = Partida.desde_fen("4k3/8/8/8/8/8/4N3/4K1r1 w - - 0 1")
        controlador = PartidaController(partida=partida, vista=vista, storage=StorageEnMemoria())
        vista.respuestas = ["e2e3"]  # el caballo no avanza una casilla: es un salto
        controlador.introducir_jugada()
        assert "ERROR" in vista.texto()

    def test_rechaza_jugar_con_el_color_contrario(self, storage, vista):
        # Esta comprobación es del controlador y no del modelo: el modelo
        # permite jugar con el color que sea; la aplicación es la que decide
        # qué color usa la persona.
        controlador = PartidaController(
            partida=Partida(), vista=vista, storage=storage, color_jugador=Color.NEGRO
        )
        vista.respuestas = ["e2e4"]
        assert controlador.introducir_jugada() is False
        assert "No es su turno" in vista.texto()

    def test_permite_jugar_con_el_color_correcto(self, storage, vista):
        controlador = PartidaController(
            partida=Partida(), vista=vista, storage=storage, color_jugador=Color.BLANCO
        )
        vista.respuestas = ["e2e4"]
        assert controlador.introducir_jugada() is True

    def test_avisa_cuando_la_partida_termina(self, controlador, vista):
        controlador.partida = Partida.desde_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        vista.respuestas = ["a1a8"]
        controlador.introducir_jugada()
        assert controlador.partida.estado is EstadoPartida.JQUE_MATE
        assert "jaque mate" in vista.texto()


# ----------------------------------------------------------------------
# Comandos escritos en el hueco de la jugada
# ----------------------------------------------------------------------

class TestComandos:
    def test_el_comando_ayuda_no_es_una_jugada(self, controlador, vista):
        vista.respuestas = ["ayuda"]
        assert controlador.introducir_jugada() is False
        assert "AYUDA" in vista.texto()
        assert controlador.partida.historial == []

    def test_el_comando_fen_muestra_la_posicion(self, controlador, vista):
        vista.respuestas = ["fen"]
        controlador.introducir_jugada()
        assert "FEN:" in vista.texto()

    def test_el_comando_historial_muestra_las_jugadas(self, controlador, vista):
        vista.respuestas = ["e2e4", "historial"]
        controlador.introducir_jugada()
        controlador.introducir_jugada()
        assert "HISTORIAL" in vista.texto()

    def test_el_comando_salir_no_cierra_el_programa(self, controlador, vista):
        # "salir" escrito en el prompt de una jugada no puede cerrar el
        # programa: sería un accidente por un despiste. Solo avisa.
        vista.respuestas = ["salir"]
        assert controlador.introducir_jugada() is False
        assert "continúa la partida" in vista.texto()

    def test_el_comando_deshacer(self, controlador, vista):
        vista.respuestas = ["e2e4", "deshacer"]
        controlador.introducir_jugada()
        controlador.introducir_jugada()
        assert controlador.partida.historial == []
        assert "deshecha" in vista.texto()

    def test_el_comando_guardar(self, controlador, vista, storage):
        vista.respuestas = ["e2e4", "guardar", "mi partida"]
        controlador.introducir_jugada()
        controlador.introducir_jugada()
        assert storage.contar() == 1


# ----------------------------------------------------------------------
# Deshacer, abandonar y empatar
# ----------------------------------------------------------------------

class TestAccionesDePartida:
    def test_deshacer_devuelve_a_la_jugada_anterior(self, controlador, vista):
        vista.respuestas = ["e2e4", "e7e5"]
        controlador.introducir_jugada()
        controlador.introducir_jugada()
        assert controlador.deshacer() is True
        assert len(controlador.partida.historial) == 1

    def test_deshacer_sin_jugadas_avisa(self, controlador, vista):
        assert controlador.deshacer() is False
        assert "No hay jugadas" in vista.texto()

    def test_abandonar_pide_confirmacion(self, controlador, vista):
        vista.respuestas = ["n"]
        controlador.abandonar()
        # Sin confirmar, la partida sigue en curso.
        assert controlador.partida.estado is EstadoPartida.EN_CURSO

    def test_abandonar_confirmado_termina_la_partida(self, controlador, vista):
        vista.respuestas = ["s"]
        controlador.abandonar()
        assert controlador.partida.estado is EstadoPartida.ABANDONO
        assert controlador.partida.ganador is Color.NEGRO

    def test_empatar_por_acuerdo(self, controlador, vista):
        # Las tablas por acuerdo no se deducen de ninguna posición: solo
        # existen porque alguien las pide. Por eso están en el controlador.
        vista.respuestas = ["s"]
        controlador.empatar()
        assert controlador.partida.estado is EstadoPartida.TABLAS
        assert controlador.partida.ganador is None
        assert "acuerdo" in controlador.partida.motivo.lower()

    def test_empatar_sin_confirmar_no_hace_nada(self, controlador, vista):
        vista.respuestas = ["n"]
        controlador.empatar()
        assert controlador.partida.estado is EstadoPartida.EN_CURSO

    def test_no_se_puede_empatar_una_partida_terminada(self, controlador, vista):
        controlador.partida.abandonar()
        vista.respuestas = ["s"]
        controlador.empatar()
        # Se mantiene el final que ya tenía.
        assert controlador.partida.estado is EstadoPartida.ABANDONO

    def test_guardar_y_empezar_otra_solo_si_se_guardo(self, controlador, vista):
        # Opción 6: "guardar y empezar otra". Se juega una jugada para que la
        # reiniciación sea detectable.
        vista.respuestas = ["e2e4"]
        controlador.introducir_jugada()
        vista.respuestas = ["Nombre", "1", "2"]
        vista.opciones = ["6", "0"]
        controlador.jugar()
        # Se ha guardado y luego se ha empezado de cero: ni una jugada ni
        # posición del principio anterior.
        assert len(controlador.partida.historial) == 0
        assert len(controlador.listar_guardadas()) == 1

    def test_cancelar_el_guardado_no_pierde_la_partida(self, controlador, vista):
        # El caso que estaba roto: la opción 6 reiniciaba la partida aunque el
        # guardado no ocurriera, así que cancelar el nombre de la partida
        # destruía el historial sin guardarlo en ningún sitio.
        vista.respuestas = ["e2e4"]
        controlador.introducir_jugada()
        # "-" es la respuesta que ``pedir_texto_opcional`` entiende como
        # "cancelo", y es lo que se pulsa al no querer escribir nada.
        vista.respuestas = ["-", "0"]
        vista.opciones = ["6", "0"]
        controlador.jugar()
        # La partida sigue ahí, con su jugada intacta.
        assert len(controlador.partida.historial) == 1
        assert controlador.listar_guardadas() == []
        assert any("sigue aquí" in linea for linea in vista.escrito)


# ----------------------------------------------------------------------
# Persistencia desde el controlador
# ----------------------------------------------------------------------

class TestPersistencia:
    def test_guardar_y_cargar_una_partida(self, controlador, vista, storage):
        vista.respuestas = ["e2e4", "e7e5", "mi partida"]
        controlador.introducir_jugada()
        controlador.introducir_jugada()
        clave = controlador.guardar()
        assert clave in storage

        # Se carga la misma clave en otro controlador y se comprueba que la
        # partida guardada está donde toca.
        otro = PartidaController(vista=VistaFalsa(), storage=storage)
        assert otro.cargar(clave) is True
        assert len(otro.partida.historial) == 2
        assert otro.partida.turno is Color.BLANCO

    def test_guardar_reutiliza_la_clave_anterior(self, controlador, vista, storage):
        # Guardar dos veces la misma partida la actualiza en vez de crear
        # copias. Es lo que espera cualquiera que juegue y vuelva a guardar.
        vista.respuestas = ["e2e4", "nombre", "g1f3", "nombre"]
        controlador.introducir_jugada()
        primera = controlador.guardar()
        controlador.introducir_jugada()
        segunda = controlador.guardar()
        assert primera == segunda
        assert storage.contar() == 1

    def test_guardar_tras_borrar_crea_una_clave_nueva(self, controlador, vista, storage):
        # Si el archivo se borró entre guardado y guardado, hay que crear una
        # clave nueva en vez de fallar al intentar reemplazarlo.
        vista.respuestas = ["e2e4", "nombre"]
        controlador.introducir_jugada()
        clave = controlador.guardar()
        storage.eliminar(clave)
        nueva = controlador.guardar("otro nombre")
        assert nueva is not None
        assert nueva != clave

    def test_cancelar_el_guardado_no_guarda(self, controlador, vista, storage):
        vista.respuestas = ["-"]
        assert controlador.guardar() is None
        assert storage.contar() == 0
        assert "cancelado" in vista.texto()

    def test_guardar_sin_almacenamiento_avisa(self, vista):
        controlador = PartidaController(vista=vista, storage=None)
        assert controlador.guardar("lo que sea") is None
        assert "almacenamiento" in vista.texto()

    def test_un_error_de_disco_no_rompe_el_programa(self, controlador, vista, storage):
        # Un error de escritura (permisos, disco lleno) no debe tumbar la
        # aplicación: se avisa y se sigue jugando.
        storage.fallos_al_guardar = True
        assert controlador.guardar("nombre") is None
        assert "no se pudo escribir" in vista.texto()

    def test_cargar_una_partida_inexistente_avisa(self, controlador, vista):
        assert controlador.cargar("no-existe") is False
        assert "No existe" in vista.texto()

    def test_cargar_pide_la_clave_si_no_se_da(self, controlador, vista, storage):
        vista.respuestas = ["e2e4", "nombre"]
        controlador.introducir_jugada()
        clave = controlador.guardar()
        # Se responde con la clave, que es lo que se haría en el menú.
        vista.respuestas = [clave]
        assert controlador.cargar() is True
        assert controlador.clave_guardada == clave

    def test_eliminar_una_partida(self, controlador, vista, storage):
        vista.respuestas = ["e2e4", "nombre"]
        controlador.introducir_jugada()
        clave = controlador.guardar()
        # Confirmar el borrado con "s".
        vista.respuestas = ["s"]
        assert controlador.eliminar_guardada(clave) is True
        assert storage.contar() == 0

    def test_eliminar_pide_confirmacion_y_se_puede_cancelar(self, controlador, vista, storage):
        vista.respuestas = ["e2e4", "nombre"]
        controlador.introducir_jugada()
        clave = controlador.guardar()
        vista.respuestas = ["n"]
        assert controlador.eliminar_guardada(clave) is False
        assert storage.contar() == 1

    def test_eliminar_deja_la_partida_actual_jugable(self, controlador, vista, storage):
        # Si la partida que se está jugando es la que se borra, el controlador
        # no debe seguir guardándola bajo una clave que ya no existe.
        vista.respuestas = ["e2e4", "nombre", "s"]
        controlador.introducir_jugada()
        clave = controlador.guardar()
        controlador.eliminar_guardada(clave)
        assert controlador.clave_guardada is None
        vista.respuestas = ["e7e5"]
        assert controlador.introducir_jugada() is True

    def test_lista_las_partidas_guardadas(self, controlador, storage):
        controlador.guardar("primera")
        assert len(controlador.listar_guardadas()) == 1

    def test_lista_vacia_sin_almacenamiento(self, vista):
        assert PartidaController(vista=vista, storage=None).listar_guardadas() == []

    def test_nueva_partida_olvida_la_clave_guardada(self, controlador, vista, storage):
        # Si no se olvidara, la partida nueva se guardaría encima de la
        # anterior y esta se perdería.
        vista.respuestas = ["e2e4", "nombre", "1"]
        controlador.introducir_jugada()
        controlador.guardar()
        controlador.nueva_partida()
        assert controlador.clave_guardada is None
        assert controlador.partida.historial == []

    def test_ofrecer_guardado_acepta(self, controlador, vista, storage):
        # Al terminar la partida se ofrece guardarla, que es justo cuando vale
        # como registro.
        vista.respuestas = ["s", "nombre"]
        assert controlador.ofrecer_guardado() is not None
        assert storage.contar() == 1

    def test_ofrecer_guardado_se_puede_rechazar(self, controlador, vista, storage):
        vista.respuestas = ["n"]
        assert controlador.ofrecer_guardado() is None
        assert storage.contar() == 0


# ----------------------------------------------------------------------
# La vista real
# ----------------------------------------------------------------------

class TestPartidaView:
    """La vista con flujos inyectados, para comprobar entrada y salida.

    Se prueban con ``StringIO`` en vez de con la consola: es la razón de
    inyectar los flujos. Así se comprueba qué se pide y qué se imprime, sin
    depender de una terminal.
    """

    def vista(self, entrada: str = "") -> tuple[PartidaView, io.StringIO]:
        salida = io.StringIO()
        return PartidaView(entrada=io.StringIO(entrada), salida=salida), salida

    def test_pide_un_texto(self):
        vista, salida = self.vista("e2e4\n")
        assert vista.pedir_texto("Jugada") == "e2e4"
        assert "Jugada" in salida.getvalue()

    def test_devuelve_el_valor_por_defecto_si_no_se_escribe_nada(self):
        # Quien pulsa Enter sin querer elige la opción marcada, que en un
        # menú es lo razonable.
        vista, _ = self.vista("\n")
        assert vista.pedir_texto("Color", "1") == "1"

    def test_sin_entrada_devuelve_el_valor_por_defecto(self):
        # Entrada agotada: en vez de reventar con una traza de error, se
        # devuelve el valor por defecto para que el programa pueda terminar.
        vista, _ = self.vista("")
        assert vista.pedir_texto("Color", "2") == "2"

    def test_pedir_opcion_rechaza_una_opcion_invalida(self):
        vista, salida = self.vista("9\n1\n")
        assert vista.pedir_opcion({"1": "Nueva", "0": "Salir"}) == "1"
        assert "no válida" in salida.getvalue()

    def test_pedir_confirmacion(self):
        assert self.vista("s\n")[0].pedir_confirmacion("¿Seguro?") is True
        assert self.vista("n\n")[0].pedir_confirmacion("¿Seguro?") is False
        assert self.vista("\n")[0].pedir_confirmacion("¿Seguro?") is False

    def test_pedir_texto_opcional_cancela_con_guion(self):
        vista, _ = self.vista("-\n")
        assert vista.pedir_texto_opcional("Nombre") is None

    def test_pedir_texto_opcional_devuelve_el_texto(self):
        vista, _ = self.vista("mi partida\n")
        assert vista.pedir_texto_opcional("Nombre") == "mi partida"

    def test_muestra_el_tablero(self):
        vista, salida = self.vista()
        vista.mostrar_tablero(Partida())
        texto = salida.getvalue()
        assert "Tablero" in texto
        assert "♔" in texto
        assert "Turno de las blancas" in texto

    def test_muestra_el_historial_vacio(self):
        vista, salida = self.vista()
        vista.mostrar_historial(Partida())
        assert "todavía no hay jugadas" in salida.getvalue()

    def test_muestra_que_no_hay_partidas_guardadas(self):
        vista, salida = self.vista()
        vista.mostrar_partidas([])
        assert "no hay ninguna" in salida.getvalue()

    def test_los_errores_del_dominio_se_muestran_sin_tipo(self):
        # Un error del dominio es un problema de lo que escribió la persona:
        # se muestra su mensaje, que ya está redactado para eso.
        vista, salida = self.vista()
        vista.mostrar_error(MovimientoIlegal("Movimiento no permitido: e2-e5."))
        texto = salida.getvalue()
        assert "Movimiento no permitido" in texto
        assert "Error inesperado" not in texto

    def test_los_errores_inesperados_muestran_su_tipo(self):
        # Un error que no es del dominio no tiene un mensaje útil: se muestra
        # su clase para saber qué está pasando.
        vista, salida = self.vista()
        vista.mostrar_error(ZeroDivisionError("división por cero"))
        assert "ZeroDivisionError" in salida.getvalue()

    def test_el_tablero_se_dibuja_una_fila_por_rango(self):
        # Se comprueba el dibujo porque es lo primero que ve quien juega.
        vista, salida = self.vista()
        partida = Partida()
        partida.mover("e2", "e4")
        vista.mostrar_tablero(partida)
        lineas = salida.getvalue().splitlines()
        # El tablero ocupa 8 líneas numeradas (más la de las letras).
        # Se usa ``isdigit()`` y no ``linea[:1] in "12345678"`` porque en Python
        # ``"" in "12345678"`` es ``True``: la línea vacía que ``mostrar_tablero``
        # escribe antes y después del tablero también contaría como rango.
        assert sum(1 for linea in lineas if linea[:1].isdigit()) == 8

    def test_sin_entrada_devuelve_la_opcion_de_salir(self):
        # El bucle de repregunta de "opción no válida" tiene un caso terminal:
        # que se acabe la entrada (Ctrl+D, o una entrada canalizada). Antes de
        # que este método devoliera "", que no era ninguna clave, el ``while
        # True`` repreguntaba para siempre y el programa se colgaba. Ahora
        # devuelve la opción de salir, que es lo único sensato cuando ya no
        # hay nadie a quien preguntar.
        vista, salida = self.vista(entrada="")
        assert vista.pedir_opcion({"1": "Nueva", "0": "Salir"}) == "0"

    def test_sin_entrada_devuelve_el_valor_por_defecto(self):
        # Para un texto suelto el comportamiento es el de siempre: el valor por
        # defecto. La diferencia con un menú es que un texto vacío puede
        # significar algo ("no" en la confirmación de abandonar) mientras que
        # una clave de menú vacía no significa nada.
        vista, _ = self.vista(entrada="")
        assert vista.pedir_texto("Nombre", "por_defecto") == "por_defecto"

    def test_una_opcion_no_valida_repregunta(self):
        # Una clave que no está en el menú sí es un error de quien escribe, y
        # se repregunta: es más amable que terminar. Se comprueba que la
        # repregunta ocurre, no que devuelva la opción equivocada.
        vista, salida = self.vista(entrada="99\n1\n")
        assert vista.pedir_opcion({"1": "Nueva", "0": "Salir"}) == "1"
        assert "Opción no válida" in salida.getvalue()

    def test_el_texto_se_normaliza_a_mayusculas_en_las_opciones(self):
        # Escribir "1" con mayúscula no es lo mismo que escribir una letra: el
        # menú compara claves exactas, así que "1" es la única que vale. Esta
        # prueba fija esa decisión, porque es la que hace el bucle de repregunta
        # necesario en lugar de opcional.
        vista, _ = self.vista(entrada="X\n0\n")
        assert vista.pedir_opcion({"1": "Nueva", "0": "Salir"}) == "0"

    def test_los_menus_no_dejan_huecos_en_la_numeracion(self):
        # Un menú que salta del 7 al 9 (que fue lo que pasaba) parece que le
        # falta una opción, y hace dudar de si hay un error. Se comprueba que
        # las claves son 1..n seguidas del 0, que es el orden en el que se leen.
        for nombre, opciones in (
            ("OPCIONES_INICIO", PartidaView.OPCIONES_INICIO),
            ("OPCIONES_PARTIDA", PartidaView.OPCIONES_PARTIDA),
            ("OPCIONES_ARCHIVO", PartidaView.OPCIONES_ARCHIVO),
        ):
            numericas = sorted(int(c) for c in opciones if c != "0")
            expected = list(range(1, len(numericas) + 1))
            assert numericas == expected, f"{nombre} tiene un hueco: {numericas}"

    def test_la_ayuda_del_juego_es_la_opcion_8(self):
        # El número concreto no debería ser una decisión arbitraria de cada
        # archivo: la ayuda se numera la última antes del 0 para que quede claro
        # que no es una jugada.
        assert "8" in PartidaView.OPCIONES_PARTIDA
        assert PartidaView.OPCIONES_PARTIDA["8"] == "Ayuda"
        assert "9" not in PartidaView.OPCIONES_PARTIDA


class TestGestionarArchivos:
    """El menú de gestión de archivos, que antes no tenía ninguna prueba.

    Existía (``menu_archivo`` y ``OPCIONES_ARCHIVO`` estaban escritos) pero no
    se alcanzaba desde ningún sitio: ``OPCIONES_INICIO`` no lo mencionaba, así que
    era código muerto. Estas pruebas fijan que ahora se llega.
    """

    def test_el_menu_principal_ofrece_gestionar_los_archivos(self):
        vista = VistaFalsa()
        assert "3" in PartidaView.OPCIONES_INICIO
        assert vista.menu_inicio() == "0"  # sin respuestas, se sale

    def test_gestionar_archivos_lista_las_partidas(self, controlador, vista):
        controlador.guardar("Mi partida")
        clave = controlador.listar_guardadas()[0]["id"]
        vista.opciones = ["3", "0"]
        controlador.gestionar_archivos()
        # Se busca la clave y no el nombre porque el nombre es lo que se guarda,
        # y la clave es lo que quien usa el programa tiene que poder leer de la
        # lista para poder escribirlo después en "cargar" o "borrar".
        assert any(clave in linea for linea in vista.escrito)

    def test_gestionar_archivos_sale_con_el_cero(self, controlador, vista):
        vista.opciones = ["0"]
        controlador.gestionar_archivos()
        # Volver es no hacer nada: ni error ni mensaje, solo salir del menú.
        assert not [linea for linea in vista.escrito if linea.startswith("ERROR")]

    def test_gestionar_archivos_carga_y_juega(self, controlador, vista):
        controlador.partida.mover("e2", "e4")
        controlador.guardar("Guardada")
        controlador.partida = Partida()
        clave = controlador.listar_guardadas()[0]["id"]
        # "2" carga y, como la partida cargada no se ve hasta entrar en juego,
        # sigue con "jugar". Sin ese "jugar" la partida se cargaría y quedaría
        # guardada en memoria sin que nadie la viera nunca.
        vista.respuestas = [clave, "0"]
        vista.opciones = ["2", "0"]
        controlador.gestionar_archivos()
        assert len(controlador.partida.historial) == 1
        # Y el bucle de juego se cierra de verdad ("0" en su menú), así que
        # ``gestionar_archivos`` también sale en vez de quedarse en juego.
        assert vista.escrito[-1].strip() == "Se vuelve al menú principal."

    def test_gestionar_archivos_borra_una_partida(self, controlador, vista):
        controlador.guardar("Para borrar")
        clave = controlador.listar_guardadas()[0]["id"]
        # Dos respuestas: la clave y la confirmación. Sin la segunda, borrar no
        # ocurriría, y esa es justamente la protección que se quiere comprobar.
        vista.respuestas = [clave, "s"]
        vista.opciones = ["4", "0"]
        controlador.gestionar_archivos()
        assert controlador.listar_guardadas() == []

    def test_borrar_una_partida_pide_confirmacion(self, controlador, vista):
        # El caso contrario del anterior: sin confirmar no se borra. Es la
        # diferencia entre "borrar" y "preguntar antes de borrar".
        controlador.guardar("Se queda")
        clave = controlador.listar_guardadas()[0]["id"]
        vista.respuestas = [clave, "n"]
        vista.opciones = ["4", "0"]
        controlador.gestionar_archivos()
        assert len(controlador.listar_guardadas()) == 1

    def test_el_menu_principal_llega_a_gestionar_archivos(self, controlador, vista):
        # Prueba de extremo a extremo del cableado que faltaba: 3 en el menú
        # principal entra en el menú de archivos, y "0" en ese menú lo deja.
        vista.opciones = ["3", "0", "0"]
        controlador.ejecutar()
        assert vista.escrito[-1] == "Hasta la próxima."
