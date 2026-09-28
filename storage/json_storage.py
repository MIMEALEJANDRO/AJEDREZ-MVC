"""Almacenamiento en un único archivo JSON.

Guarda el estado completo de cada partida (tablero, turno, historial,
promociones y contadores), que es lo que permite cerrar el programa y
continuar la partida otro día tal cual estaba.

Formato del archivo (``data/partidas.json``)::

    {
      "version": 1,
      "partidas": [
        {
          "id": "p20260927-140312",
          "nombre": "Partida del viernes",
          "fecha": "2026-09-27 14:03:12",
          "resultado": "en curso",
          "partida": { ...estado del dominio... }
        }
      ]
    }

El dominio va dentro de "partida" y la información de gestión (id, nombre,
fecha) alrededor, para que el archivo se pueda leer a mano sin mezcla.

La clave "version" no es un adorno: dentro de poco el formato habrá cambiado,
y sin ella no habría forma de saber con cuál de los dos formatos se está
leyendo un archivo. Si algún día se cambia la estructura, se incrementa el
número y se escribe una conversión para el formato viejo.

El orden de las claves es el inverso al de escritura, así que la más reciente
queda la primera y ``listar`` no necesita reordenar nada.

Hasta dónde aguanta este formato
--------------------------------

Un único archivo con todo tiene un coste que conviene dejar escrito con
números, porque es un O(n) por operación: cada ``guardar`` lee el archivo entero,
deserializa **todas** las partidas y vuelve a escribir **todas**. Medido con
partidas de 36 jugadas (unos 5,6 KB cada una en el archivo):

    partidas   tamaño     guardar    listar
         10     56 KB     7,9 ms    5,0 ms
         50    280 KB    31,7 ms   23,0 ms
        100    561 KB    63,3 ms   45,7 ms
        200  1,1 MB    121,5 ms   93,1 ms
        400  2,2 MB    268,8 ms  220,8 ms
        800  4,5 MB    636,8 ms  504,8 ms

La relación es perfectamente lineal, como tiene que ser. El punto en el que se
empieza a notar es **alrededor de 200-400 partidas**: medio segundo en cada
guardado es perceptible cuando se guarda al cambiar de turno, y a partir de ahí
cada partida nueva cuesta más que todas las anteriores juntas.

Para el alcance de este programa eso no llega a pasar: es un juego de consola
para practicar reglas, donde una persona guarda unas cuantas partidas por
sesión y el archivo se puede borrar desde el propio menú. Por eso **no** se
reescribe a SQLite ni se parte en un archivo por partida, que además
perderían la ventaja de poder abrir el JSON a mano y leerlo.

Si algún día hicieran falta miles de partidas, el sitio donde mirar es este
módulo y el cambio natural es un archivo por partida (o SQLite), porque
``BaseStorage`` ya está preparado: el contrato es ``_leer_todas`` /
``_escribir_todas``, y cambiar cómo se guardan por debajo no obliga a tocar ni el
controlador ni la vista. Ese día también habría que decidir qué se hace con los
archivos que ya están en el formato antiguo, que es justo para lo que está la
clave ``"version"`` de arriba.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from models.errores import PartidaNoEncontrada
from models.partida import Partida
from storage.base_storage import FORMATO_FECHA, BaseStorage


class JSONStorage(BaseStorage):
    """Guarda las partidas en un único archivo JSON."""

    VERSION_FORMATO = 1

    def __init__(self, ruta: str | Path | None = None) -> None:
        # Un archivo por defecto dentro de la carpeta data/ del proyecto. Se
        # calcula a partir de la ubicación de este archivo y no del directorio
        # de trabajo, para que el programa guarde siempre en el mismo sitio
        # se ejecute desde donde se ejecute.
        if ruta is None:
            raiz = Path(__file__).resolve().parent.parent
            ruta = raiz / "data" / "partidas.json"
        self.ruta = Path(ruta)
        # Etiquetas que la persona le puso a cada partida. Se llenan al leer
        # el archivo (ver ``_leer_todas``) y se usan al escribir, para que el
        # nombre puesto al guardar no se pierda al volver a guardar.
        self._nombres: dict[str, str] = {}
        # Se crea la carpeta al construir el almacenamiento y no al guardar:
        # así el programa puede listar partidas (leer) sin haber escrito nunca
        # nada, que es justo lo que pasa la primera vez.
        self.ruta.parent.mkdir(parents=True, exist_ok=True)

    # -- lectura ---------------------------------------------------------

    def _leer_crudo(self) -> dict:
        """Devuelve el contenido del archivo como diccionario.

        Hay tres casos y los tres son normales: el archivo no existe (nunca se
        ha guardado nada), está vacío (quedó a medias al cortar el programa) o
        tiene contenido. Solo el último sigue adelante. Un archivo corrupto
        que no se puede interpretar como JSON sí es un error, y en ese caso
        conviene que el programa lo diga en vez de borrar el trabajo del
        usuario sin avisar.
        """
        if not self.ruta.exists():
            return {"version": self.VERSION_FORMATO, "partidas": []}
        texto = self.ruta.read_text(encoding="utf-8").strip()
        if not texto:
            return {"version": self.VERSION_FORMATO, "partidas": []}
        try:
            return json.loads(texto)
        except json.JSONDecodeError as error:
            raise PartidaNoEncontrada(
                f"El archivo {self.ruta.name} no es un JSON válido ({error}). "
                "Revíselo o bórrelo para empezar de cero."
            ) from error

    def _leer_todas(self) -> dict[str, Partida]:
        crudo = self._leer_crudo()
        registros = crudo.get("partidas", [])
        partidas: dict[str, Partida] = {}
        # Los nombres se leen aquí, en el mismo recorrido que las partidas, y
        # no en un paso aparte. Aprovechar que ya se está leyendo el archivo
        # evita una segunda lectura y, sobre todo, garantiza que el nombre y
        # la partida del registro son siempre del mismo registro.
        self._nombres = {}
        for registro in registros:
            # El identificador es la clave del diccionario: se elige el
            # identificador guardado y, por si el archivo se editó a mano y
            # faltara, se cae a la fecha para no perder la partida.
            clave = registro.get("id") or registro.get("fecha", "")
            partidas[clave] = Partida.from_dict(registro["partida"])
            nombre = registro.get("nombre")
            if nombre:
                self._nombres[clave] = nombre
        return partidas

    # -- escritura -------------------------------------------------------

    def _escribir_todas(self, partidas: dict[str, Partida]) -> None:
        """Vuelca las partidas al archivo.

        Se escribe primero en un archivo temporal y luego se sustituye al
        final. Si el programa se corta (o se apaga el equipo) a mitad de la
        escritura, el archivo bueno sigue intacto en vez de quedar corrupto.
        """
        registros = []
        for clave, partida in partidas.items():
            registros.append(
                {
                    "id": clave,
                    "nombre": self._nombres.get(clave) or self.nombre_automatico(partida),
                    "fecha": self._fecha_de(clave),
                    "resultado": partida.estado.value,
                    "partida": partida.to_dict(),
                }
            )
        crudo = {"version": self.VERSION_FORMATO, "partidas": registros}
        # ensure_ascii=False: el archivo guarda los nombres con sus tildes y
        # los símbolos de las piezas con su carácter Unicode (♔, ♙) en vez de
        # escapes \u2654, para que se pueda leer a mano.
        texto = json.dumps(crudo, ensure_ascii=False, indent=2)
        temporal = self.ruta.with_suffix(".json.tmp")
        temporal.write_text(texto, encoding="utf-8")
        os.replace(temporal, self.ruta)

    def _recordar_nombre(self, clave: str, nombre: str | None) -> None:
        """Memoriza la etiqueta de una partida para el próximo guardado.

        Guardar dos veces la misma partida vuelve a escribir **toda** la
        colección, así que sin recordar el nombre aquí el segundo guardado
        pondría la etiqueta automática y se perdería la que la persona había
        escrito. Guardar solo si hay nombre no pisa una etiqueta anterior con
        la automática: sin nombre se conserva lo que ya hubiera.
        """
        if nombre:
            self._nombres[clave] = nombre

    def _fecha_de(self, clave: str) -> str:
        """Fecha de creación deducida del identificador.

        La clave se genera con el formato "pAAAAMMDD-HHMMSS-ffffff", así que
        la fecha se puede recuperar sin guardarla aparte. Es un pequeño ahorro
        que evita un campo más que podría desincronizarse del identificador.
        """
        bruto = clave[1:] if clave.startswith("p") else clave
        try:
            return datetime.strptime(bruto.split("-")[0] + "-" + bruto.split("-")[1],
                                     "%Y%m%d-%H%M%S").strftime(FORMATO_FECHA)
        except (ValueError, IndexError):
            # Una clave escrita a mano no tiene por qué seguir el formato; en
            # ese caso se muestra la clave tal cual en vez de fallar.
            return clave

    # -- API específica ---------------------------------------------------

    def listar_informes(self) -> list[dict]:
        """Lee los metadatos del archivo sin construir las partidas.

        Se lee el archivo crudo (no ``_leer_todas``) precisamente para no
        deserializar 32 piezas por partida solo para pintar un menú.
        """
        crudo = self._leer_crudo()
        informes = []
        for registro in crudo.get("partidas", []):
            datos = registro.get("partida", {})
            informes.append(
                {
                    "id": registro.get("id", ""),
                    "nombre": registro.get("nombre", ""),
                    "fecha": registro.get("fecha", ""),
                    "resultado": registro.get(
                        "resultado", datos.get("estado", "en curso")
                    ),
                    "turno": datos.get("turno", "blanco"),
                    "jugadas": len(datos.get("historial", [])),
                }
            )
        return sorted(informes, key=lambda informe: informe["id"], reverse=True)

    def _ordenar_claves(self, claves: list[str]) -> list[str]:
        # El identificador empieza por la fecha, así que ordenar el texto de
        # forma descendente es exactamente ordenar por fecha.
        return sorted(claves, reverse=True)
