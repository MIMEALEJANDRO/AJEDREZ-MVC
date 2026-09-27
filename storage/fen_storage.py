"""Almacenamiento en archivos de texto con notación FEN.

Cada partida se guarda en su propio archivo ``.fen`` que contiene una única
línea con la posición completa. Tiene dos ventajas sobre el JSON:

* es texto plano que se puede abrir con cualquier editor,
* es un estándar: el FEN lo entiende cualquier programa de ajedrez, así que
  estas partidas se pueden exportar e importar fuera de esta aplicación.

La contrapartida es que un FEN guarda **la posición**, no la partida. Al
recargar no hay historial, así que no se puede mostrar la notación de las
jugadas anteriores ni deshacer, ni recuperar un abandono (que es una decisión
y no una posición). Por eso el formato de por defecto del programa es el JSON.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from models.errores import PartidaNoEncontrada
from models.partida import Partida
from storage.base_storage import FORMATO_FECHA, BaseStorage


class FENStorage(BaseStorage):
    """Guarda cada partida en su propio archivo ``.fen``, con la notación estándar.

    Es la alternativa "estándar" al JSON: un archivo ``.fen`` se puede abrir en
    Lichess, en chess.com o en cualquier programa para seguir la partida, y se
    puede pegar en un foro. A cambio tiene dos limitaciones que conviene
    conocer:

    1. El FEN guarda **la posición**, no la partida. Al recargar no hay
       historial, así que no se puede mostrar la notación de las jugadas
       anteriores ni deshacer.
    2. Solo admite una partida en curso por archivo. El formato es una
       posición, no un conjunto de posiciones.

    Aun así es útil y por eso existe: es la forma de exportar la partida fuera
    del programa.

    Cada archivo contiene una sola línea con el FEN, cuyo nombre es el
    identificador (``pAAAAMMDD-HHMMSS.fen``).
    """

    def __init__(self, carpeta: str | Path | None = None) -> None:
        if carpeta is None:
            raiz = Path(__file__).resolve().parent.parent
            carpeta = raiz / "data" / "fen"
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)

    def _ruta_de(self, clave: str) -> Path:
        """Ruta del archivo de una partida, a partir del identificador.

        Se recorta la extensión si el usuario la escribe, y se rechazan los
        identificadores con separadores de ruta: sin esa comprobación, un
        nombre como "../../otro_archivo" escribiría fuera de la carpeta de
        partidas. Es un tipo de ataque (recorrido de directorios) que en un
        programa local es poco grave, pero que se evita con dos líneas.
        """
        limpio = self._normalizar(clave)
        if not limpio or any(separador in limpio for separador in ("/", "\\", "..")):
            raise PartidaNoEncontrada(f"Identificador de partida no válido: {clave!r}.")
        return self.carpeta / f"{limpio}.fen"

    def _normalizar(self, clave: str) -> str:
        """Quita la extensión ``.fen`` si viene puesta.

        Quien escribe la clave a mano la copia de la lista de la pantalla o
        del explorador de archivos, y en un caso lleva extensión y en el otro
        no. Aceptar las dos formas evita un "no existe" desconcertante.
        """
        return clave[:-4] if clave.endswith(".fen") else clave

    # -- lectura ---------------------------------------------------------

    def _leer_todas(self) -> dict[str, Partida]:
        partidas: dict[str, Partida] = {}
        for archivo in self.carpeta.glob("*.fen"):
            texto = archivo.read_text(encoding="utf-8").strip()
            if not texto:
                # Un archivo vacío no es un error: se ignora y se sigue con el
                # resto, en vez de impedir cargar todas las partidas.
                continue
            partidas[archivo.stem] = Partida.desde_fen(texto)
        return partidas

    # -- escritura -------------------------------------------------------

    def _escribir_todas(self, partidas: dict[str, Partida]) -> None:
        """Escribe un archivo por partida y borra los que ya no están.

        A diferencia del JSON, aquí no se puede limitar a "volcar el diccionario"
        porque el soporte es un conjunto de archivos: si una partida se
        borrara del diccionario y no se borrara su archivo, volvería a aparecer
        al listar. Por eso se recorre la carpeta y se elimina lo que no esté en
        el diccionario.
        """
        for clave, partida in partidas.items():
            self._ruta_de(clave).write_text(partida.a_fen() + "\n", encoding="utf-8")
        for archivo in self.carpeta.glob("*.fen"):
            if archivo.stem not in partidas:
                archivo.unlink()

    def _ordenar_claves(self, claves: list[str]) -> list[str]:
        return sorted(claves, key=self._mtime_de, reverse=True)

    def _mtime_de(self, clave: str) -> float:
        """Fecha de modificación del archivo, como marca de tiempo.

        Es lo único que hay de "fecha" en este formato: el FEN no lleva
        metadatos, así que la hora del sistema es la única información de
        cuándo se guardó.
        """
        archivo = self._ruta_de(clave)
        return archivo.stat().st_mtime if archivo.exists() else 0.0

    # -- API específica ---------------------------------------------------

    def listar_informes(self) -> list[dict]:
        """Informe de cada archivo ``.fen``.

        El FEN no lleva metadatos, así que aquí no hay atajo: hay que
        interpretarlo con ``Partida.desde_fen``, que ya distingue mate de
        ahogado y calcula los finales. Para un menú de diez partidas el coste
        es irrelevante y la información es correcta.
        """
        informes = []
        for archivo in self.carpeta.glob("*.fen"):
            texto = archivo.read_text(encoding="utf-8").strip()
            if not texto:
                continue
            partida = Partida.desde_fen(texto)
            informes.append(
                {
                    "id": archivo.stem,
                    "nombre": self.nombre_automatico(partida),
                    "fecha": datetime.fromtimestamp(archivo.stat().st_mtime).strftime(FORMATO_FECHA),
                    "resultado": partida.estado.value,
                    "turno": partida.turno.value,
                    "jugadas": self._jugadas_jugadas(partida),
                }
            )
        return sorted(informes, key=lambda informe: self._mtime_de(informe["id"]), reverse=True)

    def _jugadas_jugadas(self, partida: Partida) -> int:
        """Número de medios movimientos jugados que se deducen del FEN.

        El FEN lleva la jugada completa (``numero_movimiento``) y de quién es el
        turno, y de ahí sale el número de medias jugadas: en la jugada 2 con
        turno blanco se han hecho dos medias jugadas (blanca y negra). No es un
        dato guardado, es un cálculo de una línea.

        Ojo: al recargar un FEN el historial está vacío, así que esto no
        significa que se pueda deshacer; solo sirve para pintar el menú.
        """
        return (partida.numero_movimiento - 1) * 2 + (1 if partida.turno.value == "negro" else 0)
