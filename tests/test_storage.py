"""Pruebas de la persistencia: JSON y FEN.

Las dos implementaciones de ``BaseStorage`` se prueban con la **misma** batería
de pruebas. Es la forma de comprobar de verdad que cumplen el mismo contrato:
si las dos pasan lo mismo, el controlador puede usarlas indistintamente, que es
justo la propiedad que justifica que exista la clase abstracta.

Todas las pruebas usan ``tmp_path``, la carpeta temporal que crea pytest para
cada prueba. Con eso no queda ni un archivo en el proyecto y las pruebas se
pueden repetir sin sorpresas.
"""

import json

import pytest

from models.enums import Color, EstadoPartida, TipoPieza
from models.errores import PartidaNoEncontrada
from models.partida import Partida
from models.posicion import Posicion
from storage.fen_storage import FENStorage
from storage.json_storage import JSONStorage

# Se parametriza la clase: pytest genera una copia de cada prueba para cada
# almacenamiento. Añadir un tercer formato (por ejemplo CSV) es añadir su
# nombre a esta tupla, sin tocar ni una de estas pruebas.
ALMACENAMIENTOS = [JSONStorage, FENStorage]


@pytest.fixture(params=ALMACENAMIENTOS)
def storage(request, tmp_path):
    """Cada prueba se ejecuta contra JSON y contra FEN, con carpetas distintas.

    Cada almacenamiento recibe su propia subcarpeta temporal: si compartieran
    carpeta, un archivo del JSON podría aparecer como si fuera del FEN y las
    pruebas pasarían por casualidad.
    """
    clase = request.param
    if clase is JSONStorage:
        return clase(tmp_path / "datos" / "partidas.json")
    return clase(tmp_path / "datos" / "fen")


def partida_con_jugadas() -> Partida:
    """Partida de ejemplo: apertura normal (1.e4 c5), con **dos jugadas**.

    Ojo con el turno: después de la jugada de las negras vuelve a tocar a las
    blancas, así que el turno de esta partida es el blanco.
    """
    partida = Partida()
    partida.mover("e2", "e4")
    partida.mover("c7", "c5")
    return partida


# ----------------------------------------------------------------------
# Contrato común
# ----------------------------------------------------------------------

class TestContratoComun:
    def test_una_partida_nueva_esta_vacia(self, storage):
        # "No hay partidas" es el estado normal la primera vez, no un error.
        assert storage.listar() == []
        assert storage.contar() == 0
        assert len(storage) == 0

    def test_guardar_y_listar(self, storage):
        clave = storage.guardar(partida_con_jugadas())
        partidas = storage.listar()
        assert len(partidas) == 1
        # Tras 1.e4 c5 vuelve a tocar a las blancas.
        assert partidas[0].turno is Color.BLANCO
        assert clave

    def test_guardar_y_cargar_conserva_la_posicion(self, storage):
        # Lo que los dos formatos comparten es la **posición**: el FEN debe
        # ser idéntico antes y después del viaje. El historial solo lo guarda el
        # JSON (ver ``TestJSONStorage``): el FEN no tiene dónde anotarlo.
        original = partida_con_jugadas()
        clave = storage.guardar(original)
        cargada = storage.cargar(clave)
        assert cargada.a_fen() == original.a_fen()
        assert cargada.turno is original.turno
        assert cargada.tablero.clave() == original.tablero.clave()

    def test_guardar_con_la_misma_clave_actualiza(self, storage):
        # Volver a guardar la misma partida **con su clave** la actualiza. Sin
        # esto, jugar y guardar tres veces dejaría tres archivos idénticos.
        partida = partida_con_jugadas()
        clave = storage.guardar(partida)
        partida.mover("g1", "f3")
        storage.guardar(partida, clave=clave)
        assert storage.contar() == 1
        assert storage.cargar(clave).a_fen() == partida.a_fen()

    def test_guardar_sin_clave_crea_una_partida_nueva(self, storage):
        # El caso contrario del anterior, y la razón de que la clave sea un
        # parámetro opcional: si quien guarda no dice qué clave quiere, se
        # genera una nueva y la partida anterior se queda como estaba.
        partida = partida_con_jugadas()
        storage.guardar(partida)
        partida.mover("g1", "f3")
        storage.guardar(partida)
        assert storage.contar() == 2

    def test_varias_partidas_conviven(self, storage):
        primera = storage.guardar(partida_con_jugadas(), "primera")
        segunda = storage.guardar(partida_con_jugadas(), "segunda")
        assert storage.contar() == 2
        assert primera != segunda
        assert set(storage._leer_todas()) == {primera, segunda}

    def test_cargar_una_partida_inexistente_da_error(self, storage):
        # El error es el mismo venga del JSON o del FEN, y es la razón de ser
        # de ``PartidaNoEncontrada``.
        with pytest.raises(PartidaNoEncontrada):
            storage.cargar("no-existe")

    def test_eliminar_una_partida(self, storage):
        clave = storage.guardar(partida_con_jugadas())
        assert storage.eliminar(clave) is True
        assert storage.contar() == 0

    def test_eliminar_una_partida_inexistente_devuelve_false(self, storage):
        # Borrar lo que no existe no es un error del programa: es una
        # situación normal (el archivo pudo borrarse a mano).
        assert storage.eliminar("no-existe") is False

    def test_existe_y_operador_in(self, storage):
        clave = storage.guardar(partida_con_jugadas())
        assert storage.existe(clave) is True
        assert clave in storage
        assert "no-existe" not in storage

    def test_las_partidas_se_listan_de_la_mas_reciente(self, storage):
        # Lo que se está usando es lo último que se guardó, así que va
        # primero. Como la clave lleva la fecha con segundos, dos guardados
        # seguidos siempre tienen orden distinto.
        primera = storage.guardar(partida_con_jugadas(), "primera")
        segunda = storage.guardar(partida_con_jugadas(), "segunda")
        assert storage.listar()[0].a_fen() == storage.cargar(segunda).a_fen()
        assert storage.listar()[1].a_fen() == storage.cargar(primera).a_fen()

    def test_una_partida_terminada_se_guarda_y_se_carga_terminada(self, storage):
        # El caso que más se va a necesitar: dejar la partida guardada cuando
        # alguien ya no puede jugar.
        #
        # Se usa un jaque mate y no un abandono a propósito: el mate se deduce
        # de la posición, así que los dos formatos lo conservan. El abandono no
        # se puede deducir de un FEN (es una decisión, no una posición) y solo
        # lo guarda el JSON (ver ``TestJSONStorage``).
        partida = Partida.desde_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
        partida.mover("a1", "a8")
        clave = storage.guardar(partida)
        assert storage.cargar(clave).estado is EstadoPartida.JAQUE_MATE

    def test_los_derechos_de_enroque_sobreviven_al_viaje(self, storage):
        # Los derechos de enroque no se deducen de las piezas (dependen del
        # historial), así que son el dato más fácil de perder al serializar.
        # Por eso se comprueba explícitamente.
        partida = Partida()
        clave = storage.guardar(partida)
        assert storage.cargar(clave).tablero.derechos_enroque == {"K", "Q", "k", "q"}

    def test_informes_de_todas_las_partidas(self, storage):
        storage.guardar(partida_con_jugadas(), "primera")
        storage.guardar(partida_con_jugadas(), "segunda")
        informes = storage.listar_informes()
        assert len(informes) == 2
        for informe in informes:
            # Cada informe tiene lo mínimo para pintar el menú, y ese
            # mínimo se comprueba aquí para que no se rompa al tocar el
            # formato de guardado.
            assert set(informe) >= {"id", "nombre", "fecha", "resultado"}
            assert informe["id"]

    def test_informes_de_una_partida_en_juego(self, storage):
        clave = storage.guardar(partida_con_jugadas())
        informe = storage.listar_informes()[0]
        assert informe["id"] == clave
        assert informe["resultado"] == "en curso"
        # Después de 1.e4 c5 vuelve a tocar a las blancas.
        assert informe["turno"] == "blanco"
        # Las dos jugadas jugadas. En el JSON se cuentan directamente; en el
        # FEN se deducen del número de jugada y del turno (ver
        # ``FENStorage._jugadas_jugadas``).
        assert informe["jugadas"] == 2

    def test_repr_muestra_el_numero_de_partidas(self, storage):
        storage.guardar(partida_con_jugadas())
        assert "1" in repr(storage)


# ----------------------------------------------------------------------
# Detalles de JSONStorage
# ----------------------------------------------------------------------

class TestJSONStorage:
    def test_crea_la_carpeta_si_no_existe(self, tmp_path):
        # Así el programa puede listar partidas sin haber escrito nunca nada.
        destino = tmp_path / "a" / "b" / "partidas.json"
        JSONStorage(destino)
        assert destino.parent.is_dir()

    def test_crea_el_archivo_vacio_al_guardar(self, tmp_path):
        destino = tmp_path / "partidas.json"
        storage = JSONStorage(destino)
        storage.guardar(partida_con_jugadas())
        assert destino.exists()

    def test_el_archivo_tiene_forma_json_legible(self, tmp_path):
        destino = tmp_path / "partidas.json"
        JSONStorage(destino).guardar(partida_con_jugadas(), "mi partida")
        crudo = json.loads(destino.read_text(encoding="utf-8"))
        assert crudo["version"] == 1
        assert len(crudo["partidas"]) == 1
        registro = crudo["partidas"][0]
        # Se guarda el dominio dentro de "partida", y la información de
        # gestión (id, nombre, fecha) alrededor. Así el archivo se puede leer
        # a mano sin mezcla.
        assert "partida" in registro
        assert registro["nombre"] == "mi partida"

    def test_los_acentos_se_guardan_sin_escapes(self, tmp_path):
        # ensure_ascii=False: el archivo se lee con los caracteres tal cual, no
        # con escapes \uXXXX, que es mucho más legible para quien lo abra.
        #
        # Ojo: los símbolos de las piezas (♔) **no** aparecen en el JSON, porque
        # el tablero se serializa en notación FEN ("K", "R"...), que es la
        # forma estándar de intercambio. Lo que se comprueba aquí es la
        # escritura sin escapes, con un nombre con tildes y eñes.
        destino = tmp_path / "partidas.json"
        JSONStorage(destino).guardar(Partida(), "Partida de añejos y café")
        texto = destino.read_text(encoding="utf-8")
        assert "\\u" not in texto
        assert "Partida de añejos y café" in texto

    def test_el_historial_sobrevive_al_viaje(self, tmp_path):
        # El JSON sí guarda la partida completa, no solo la posición: al recargar
        # se puede seguir viendo la notación y deshacer jugadas.
        storage = JSONStorage(tmp_path / "partidas.json")
        original = partida_con_jugadas()
        cargada = storage.cargar(storage.guardar(original))
        assert [m.notacion for m in cargada.historial] == [
            m.notacion for m in original.historial
        ]

    def test_sobrevive_el_abandono(self, tmp_path):
        # Un abandono no se puede deducir de una posición (es una decisión), así
        # que solo un formato que guarde el estado completo, como el JSON, puede
        # conservarlo.
        storage = JSONStorage(tmp_path / "partidas.json")
        partida = Partida()
        partida.abandonar()
        cargada = storage.cargar(storage.guardar(partida))
        assert cargada.estado is EstadoPartida.ABANDONO
        assert cargada.ganador is Color.NEGRO
        assert "abandonaron" in cargada.motivo

    def test_sobrevive_una_promocion_que_no_es_dama(self, tmp_path):
        # Sin guardar la promoción, deshacer un peón promovido a torre lo
        # convertiría en dama. Esta prueba es la que cubre ese caso.
        storage = JSONStorage(tmp_path / "partidas.json")
        partida = Partida.desde_fen("8/P6k/8/8/8/8/8/4K3 w - - 0 1")
        partida.mover("a7", "a8", "torre")
        cargada = storage.cargar(storage.guardar(partida))
        assert cargada.tablero.obtener(Posicion(0, 7)).tipo is TipoPieza.TORRE
        cargada.deshacer()
        # Al deshacer, la torre desaparece de a8 y el peón vuelve a a7: si la
        # promoción se hubiera perdido, en a8 habría una dama.
        assert cargada.tablero.obtener(Posicion(0, 7)) is None
        assert cargada.tablero.obtener(Posicion(0, 6)).tipo is TipoPieza.PEON
        assert len(cargada.historial) == 0

    def test_el_nombre_se_usa_al_guardar_y_se_conserva_al_volver_a_guardar(self, tmp_path):
        storage = JSONStorage(tmp_path / "partidas.json")
        clave = storage.guardar(Partida(), "primera vez")
        assert storage.listar_informes()[0]["nombre"] == "primera vez"
        # Al volver a guardar **con la misma clave** el nombre se queda, en vez
        # de que cada guardado ponga la etiqueta automática.
        storage.guardar(Partida(), clave=clave)
        assert storage.listar_informes()[0]["nombre"] == "primera vez"

    def test_un_archivo_vacio_se_trata_como_sin_partidas(self, tmp_path):
        # Un archivo vacío significa que el programa se cortó al escribir: es
        # un estado recuperable, no un error.
        destino = tmp_path / "partidas.json"
        destino.write_text("", encoding="utf-8")
        assert JSONStorage(destino).listar() == []

    def test_un_archivo_corrupto_avisa_en_vez_de_borrar_todo(self, tmp_path):
        # Si el JSON está dañado, lo correcto es decirlo y no seguir, porque
        # lo que hay dentro puede ser trabajo perdido.
        destino = tmp_path / "partidas.json"
        destino.write_text("{esto no es json", encoding="utf-8")
        with pytest.raises(PartidaNoEncontrada):
            JSONStorage(destino).listar()

    def test_no_deja_archivos_temporales(self, tmp_path):
        # La escritura es "en temporal y renombrar", y al final no debe quedar
        # ningún resto del temporal.
        destino = tmp_path / "partidas.json"
        storage = JSONStorage(destino)
        storage.guardar(partida_con_jugadas())
        assert not list(tmp_path.glob("*.tmp"))

    def test_el_fen_generado_solo_tiene_las_casillas_ocupadas(self, tmp_path):
        # Se comprueba que el FEN de un tablero vacío es "8/8/.../8", que es
        # donde más fácil se equivoca uno al agrupar casillas vacías.
        partida = Partida()
        partida.tablero.limpiar()
        assert partida.a_fen().split(" ")[0] == "8/8/8/8/8/8/8/8"


# ----------------------------------------------------------------------
# Detalles de FENStorage
# ----------------------------------------------------------------------

class TestFENStorage:
    def test_crea_un_archivo_por_partida(self, tmp_path):
        carpeta = tmp_path / "fen"
        storage = FENStorage(carpeta)
        clave = storage.guardar(partida_con_jugadas())
        assert (carpeta / f"{clave}.fen").exists()

    def test_el_archivo_contiene_un_solo_fen(self, tmp_path):
        carpeta = tmp_path / "fen"
        storage = FENStorage(carpeta)
        clave = storage.guardar(partida_con_jugadas())
        lineas = (carpeta / f"{clave}.fen").read_text(encoding="utf-8").strip().splitlines()
        # Una línea: un FEN de tablero es siempre una línea sola. Que se pueda
        # abrir en otro programa depende de esto.
        assert len(lineas) == 1
        assert lineas[0].count(" ") == 5  # los 6 campos del FEN

    def test_el_archivo_no_lleva_acentos_nada_extra(self, tmp_path):
        # El archivo es FEN puro, sin metadatos ni comentarios, para que otro
        # programa pueda leerlo sin que entienda nada de este.
        carpeta = tmp_path / "fen"
        storage = FENStorage(carpeta)
        clave = storage.guardar(Partida())
        texto = (carpeta / f"{clave}.fen").read_text(encoding="utf-8")
        assert Partida().a_fen() in texto

    def test_el_fen_recupera_la_posicion_exacta(self, tmp_path):
        storage = FENStorage(tmp_path / "fen")
        original = partida_con_jugadas()
        clave = storage.guardar(original)
        assert storage.cargar(clave).a_fen() == original.a_fen()

    def test_el_fen_no_conserva_el_historial(self, tmp_path):
        # Limitación conocida y documentada: el FEN guarda la posición, no la
        # partida. Se comprueba para que quede escrito en la prueba y no se
        # descubra de repente al usar el programa.
        storage = FENStorage(tmp_path / "fen")
        clave = storage.guardar(partida_con_jugadas())
        assert storage.cargar(clave).historial == []

    def test_el_fen_no_conserva_el_abandono(self, tmp_path):
        # Tampoco el estado de "abandono": un FEN de una posición con piezas no
        # dice si se abandonó o se simplemente se dejó a medias. Al recargarlo,
        # el modelo lo recalcula y la partida sigue "en curso". Es la otra mitad
        # de la limitación del FEN, y por eso el formato de por defecto del
        # programa es el JSON.
        storage = FENStorage(tmp_path / "fen")
        partida = Partida()
        partida.abandonar()
        assert storage.cargar(storage.guardar(partida)).estado is EstadoPartida.EN_CURSO

    def test_el_fen_conserva_los_derechos_de_enroque(self, tmp_path):
        # Aunque no conserve el historial, sí los derechos, porque van en el
        # propio FEN. Es lo que hace que una partida recargada siga pudiendo
        # enrocar.
        storage = FENStorage(tmp_path / "fen")
        clave = storage.guardar(Partida())
        assert storage.cargar(clave).tablero.derechos_enroque == {"K", "Q", "k", "q"}

    def test_un_archivo_vacio_se_ignora(self, tmp_path):
        # Un archivo vacío no debe impedir ver el resto de las partidas.
        carpeta = tmp_path / "fen"
        storage = FENStorage(carpeta)
        storage.guardar(partida_con_jugadas())
        (carpeta / "basura.fen").write_text("", encoding="utf-8")
        assert storage.contar() == 1

    def test_eliminar_borra_el_archivo(self, tmp_path):
        # En JSON basta con quitar la entrada; aquí hay que borrar el archivo,
        # o reaparecería al listar.
        carpeta = tmp_path / "fen"
        storage = FENStorage(carpeta)
        clave = storage.guardar(partida_con_jugadas())
        storage.eliminar(clave)
        assert not (carpeta / f"{clave}.fen").exists()
        assert storage.contar() == 0

    def test_acepta_la_clave_con_o_sin_extension(self, tmp_path):
        # Quien escribe la clave a mano le pone extensión o no, según el
        # programa desde el que copió. Las dos formas deben funcionar.
        storage = FENStorage(tmp_path / "fen")
        clave = storage.guardar(partida_con_jugadas())
        assert storage.cargar(clave + ".fen").a_fen() == storage.cargar(clave).a_fen()

    def test_rechaza_identificadores_con_ruta(self, tmp_path):
        # Un identificador con ".." o con una barra escribiría fuera de la
        # carpeta de partidas. Se comprueba que se rechaza.
        storage = FENStorage(tmp_path / "fen")
        for clave_mala in ("../fuera", "a/b", "", ".."):
            with pytest.raises(PartidaNoEncontrada):
                storage._ruta_de(clave_mala)
