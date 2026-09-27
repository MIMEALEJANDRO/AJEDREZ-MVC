"""Contrato común de los almacenamientos (persistencia).

Un *almacenamiento* es lo único del programa que toca el disco. Todas las
implementaciones cumplen el mismo contrato, definido en ``BaseStorage``:

    guardar   ->  listar   ->  cargar   ->  eliminar

Gracias a eso el controlador no sabe si una partida se guarda en un JSON o en
un archivo ``.fen``: pide "guarda esto" y "carga la partida 3" sin preguntar
nunca por el formato.

El motivo de la separación es el mismo que en el resto del proyecto: las
reglas de ajedrez no deben enterarse de que existen los archivos. Si
``Partida.mover`` escribiera en disco, sería imposible probar las reglas sin
escribir archivos de verdad, y cambiar de formato obligaría a tocar el modelo.

Este módulo contiene **solo** el contrato. Cada formato tiene su propio módulo
(``json_storage.py`` y ``fen_storage.py``): un archivo que define el contrato y
las implementaciones a la vez obliga a leerlo entero para saber dónde está cada
cosa, y hace que cambiar un formato parezca que toca el contrato cuando no es
así.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from models.errores import PartidaNoEncontrada
from models.partida import Partida

# Fecha y hora en formato "2026-09-27 14:03:12". Se usa ``strftime`` con
# separadores legibles en vez de un ISO con "T" porque es lo que se muestra en
# pantalla, y la pantalla es el destino de este dato.
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"


class BaseStorage(ABC):
    """Clase abstracta que define el contrato de todos los almacenamientos.

    Hereda de ``ABC``: así el intento de instanciar una subclase que no implemente
    todos los métodos abstractos falla al crearla y no al usarla, que es cuando
    el error sería más difícil de encontrar.
    """

    # ------------------------------------------------------------------
    # API pública: la que usa el controlador
    # ------------------------------------------------------------------

    def guardar(
        self,
        partida: Partida,
        nombre: str | None = None,
        clave: str | None = None,
    ) -> str:
        """Guarda una partida y devuelve su identificador.

        ``nombre`` es la etiqueta que le puso la persona que juega ("Partida
        del viernes"). Si no se indica se usa una etiqueta automática con la
        posición de la partida.

        ``clave`` es la clave con la que se guarda. Si no se indica se genera
        una nueva; si se indica, la partida se guarda **con esa clave**,
        reemplazando lo que hubiera. Es lo que hace el controlador al volver a
        guardar una partida que ya estaba guardada, y por eso es un parámetro y
        no un detalle interno: quien llama es quien sabe si está creando una
        entrada nueva o actualizando una existente.
        """
        partidas = self._leer_todas()
        if clave is None:
            clave = self.generar_clave(partida, nombre)
        else:
            clave = self._normalizar(clave)
        partidas[clave] = partida
        # La etiqueta se apunta antes de escribir: la usa ``_escribir_todas``
        # para saber qué nombre poner en el registro de esta clave.
        self._recordar_nombre(clave, nombre)
        self._escribir_todas(partidas)
        return clave

    def listar(self) -> list[Partida]:
        """Todas las partidas guardadas, de la más reciente a la más antigua.

        El orden importa: lo que se está usando es lo último guardado, así que
        va primero. Cada implementación decide cómo se ordena, pero todas
        devuelven la más reciente primero.
        """
        partidas = self._leer_todas()
        claves = self._ordenar_claves(claves=list(partidas.keys()))
        return [partidas[clave] for clave in claves]

    def cargar(self, clave: str) -> Partida:
        """Recupera una partida por su identificador.

        Lanza
        -----
        PartidaNoEncontrada
            Si no existe. Es la excepción que ``errores.py`` reserva para esto
            justamente para que el controlador capture siempre lo mismo,
            venga el error del JSON o del FEN.
        """
        clave = self._normalizar(clave)
        partidas = self._leer_todas()
        if clave not in partidas:
            raise PartidaNoEncontrada(f"No existe ninguna partida con el identificador {clave!r}.")
        return partidas[clave]

    def eliminar(self, clave: str) -> bool:
        """Borra una partida. Devuelve ``True`` si existía, ``False`` si no.

        Devolver un booleano en vez de lanzar excepción es una decisión
        consciente: preguntar "¿borrar esta partida que no existe?" es un caso
        normal (el archivo pudo borrarse a mano) y no un error del programa.
        """
        clave = self._normalizar(clave)
        partidas = self._leer_todas()
        if clave not in partidas:
            return False
        del partidas[clave]
        self._escribir_todas(partidas)
        return True

    def existe(self, clave: str) -> bool:
        """True si hay una partida guardada con ese identificador."""
        return self._normalizar(clave) in self._leer_todas()

    def contar(self) -> int:
        """Cuántas partidas hay guardadas."""
        return len(self._leer_todas())

    def __len__(self) -> int:
        return self.contar()

    def __contains__(self, clave: str) -> bool:
        """Permite escribir ``"abc" in storage`` en vez de ``storage.existe("abc")``."""
        return self.existe(clave)

    # ------------------------------------------------------------------
    # API interna: la que implementa cada almacenamiento
    # ------------------------------------------------------------------

    def generar_clave(self, partida: Partida, nombre: str | None = None) -> str:
        """Construye el identificador con el que se guarda la partida.

        Se compone de la fecha y hora **con microsegundos**. Los microsegundos
        no son un detalle gratuito: sin ellos, dos partidas guardadas en el
        mismo segundo reciben la misma clave y la segunda machaca a la
        primera. En las pruebas se guardan partidas seguidas y se nota enseguida.

        El prefijo "p" evita que un identificador empiece por un dígito, que es
        lo que algunos programas leen como un número.
        """
        marca = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        return f"p{marca}"

    def nombre_automatico(self, partida: Partida) -> str:
        """Etiqueta por defecto de una partida, cuando no se le dio nombre.

        No hay un campo "nombre" en el dominio (no es un dato del juego), así
        que se usa la posición: el turno y el número de jugada dicen en qué
        punto está la partida, que es justo lo que se quiere ver en la lista.

        Se usa ``Color.nombre_legible`` ("Blancas" / "Negras") y no el valor
        del enum ("blanco" / "negro") porque con el valor salen "Turno de las
        blancos", que es un error de concordancia.
        """
        return f"Turno de {partida.turno.nombre_legible.lower()} (jugada {partida.numero_movimiento})"

    def _normalizar(self, clave: str) -> str:
        """Deja la clave en la forma que usa este almacenamiento.

        La base devuelve la clave tal cual. Los almacenamientos que trabajan
        con archivos (donde el nombre del archivo lleva extensión) la
        reescriben, para que escribir "clave.fen" y "clave" signifiquen lo
        mismo.
        """
        return clave

    def _recordar_nombre(self, clave: str, nombre: str | None) -> None:
        """Guarda la etiqueta que la persona le puso a una partida.

        La base no guarda nada: no todos los formatos tienen dónde poner un
        nombre. Los que sí (el JSON) lo reescriben.
        """

    @abstractmethod
    def _leer_todas(self) -> dict[str, Partida]:
        """Lee todas las partidas y las devuelve como ``{clave: Partida}``.

        Si no hay ninguna guardada devuelve un diccionario vacío, nunca
        ``None`` y nunca un error: "no hay partidas" es el estado normal la
        primera vez que se abre el programa.
        """

    @abstractmethod
    def _escribir_todas(self, partidas: dict[str, Partida]) -> None:
        """Vuelca todas las partidas en el soporte y cierra el archivo.

        Se implementa siempre *reescribiendo el conjunto entero* en vez de
        tocar un archivo suelto. Con pocas partidas es lo más simple y no hay
        ningún coste apreciable; el día que hubiera millones de partidas se
        cambiaría por un fichero por partida, pero ese no es el caso de un
        juego de consola.
        """

    @abstractmethod
    def _ordenar_claves(self, claves: list[str]) -> list[str]:
        """Ordena las claves de la más reciente a la más antigua."""

    @abstractmethod
    def listar_informes(self) -> list[dict]:
        """Resumen de cada partida guardada, sin construir el objeto ``Partida``.

        Existe para que listar el contenido de la carpeta no obligue a
        deserializar 32 piezas por partida solo para pintar un menú. Cada
        implementación tiene sus propios datos (un JSON tiene nombre y fecha
        guardados; un FEN solo tiene la fecha del archivo), así que devuelve
        diccionarios sueltos en vez de un tipo común: es la información
        mínima que la vista necesita y nada más.

        Es abstracta (y no un ``NotImplementedError``) porque las dos
        implementaciones la necesitan de verdad: si algún día se añadiera un
        tercer formato y se olvidara de ella, el fallo aparecería al pintar el
        menú, lejos de la causa.
        """

    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self)} partidas)"
