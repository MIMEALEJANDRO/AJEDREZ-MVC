"""Punto de entrada del programa de ajedrez.

Este archivo tiene una única responsabilidad: **configurar**. Decide dónde se
guardan las partidas, qué vista se usa y de qué color se juega, construye el
controlador con esos colaboradores y lo arranca.

Todo lo demás vive en las capas:

* ``models/``         — las reglas (ni idea de qué es un menú o un archivo),
* ``storage/``        — los archivos (ni idea de qué es una regla),
* ``views/``          — la pantalla (ni idea de qué es una regla),
* ``controllers/``    — el que une las tres.

Que el arranque sea tan corto no es casualidad: es lo que hace que cambiar de
formato de guardado, de pantalla o de reglas no toque este archivo. Si algún
día hace falta aquí más de unas decenas de líneas, es una señal de que algo se
ha metido en la capa equivocada.

Uso::

    python main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Se añade la raíz del proyecto al `sys.path` para que los imports absolutos
# (`from models import Partida`) funcionen se ejecute el programa desde donde
# se ejecute. Es la solución estándar para un proyecto que no se instala con
# `pip`; un `pip install -e .` lo haría innecesario, pero para un ejercicio de
# consola es la opción que menos cosas exige.
RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from controllers.partida_controller import PartidaController  # noqa: E402
from storage.fen_storage import FENStorage  # noqa: E402
from storage.json_storage import JSONStorage  # noqa: E402
from views.partida_view import PartidaView  # noqa: E402

# Carpeta donde se guardan las partidas. Se resuelve a partir de la ubicación
# de este archivo para que las partidas se guarden siempre en el proyecto y no
# en el directorio desde el que se haya ejecutado el programa.
CARPETA_DATOS = RAIZ / "data"

# Las opciones de guardado se declaran como diccionario y no como varios
# `if`: añadir un formato (por ejemplo un CSV) es añadir una línea, y el bucle
# de abajo no cambia. La clave es lo que escribe la persona y el valor es lo
# que se construye.
ALMACENAMIENTOS = {
    "1": ("JSON (guarda todo, con historial)", lambda: JSONStorage(CARPETA_DATOS / "partidas.json")),
    "2": ("FEN  (un archivo por partida, estándar)", lambda: FENStorage(CARPETA_DATOS / "fen")),
}

# Se elige el almacenamiento con una función aparte y no dentro de
# `main()`, para que la pregunta no se mezcle con la construcción de objetos.
# Así esta función se puede probar sola.
def elegir_almacenamiento(vista: PartidaView):
    """Muestra el menú de formato y devuelve el almacenamiento elegido.

    Se pide el formato *una vez*, al arrancar, y no en cada guardado. Es la
    decisión de diseño que hace que cambiar de formato no se pueda hacer por
    error a mitad de una partida (que dejaría la partida guardada a medias en
    dos sitios distintos).
    """
    while True:
        vista.titulo("Formato de guardado")
        for clave, (descripcion, _) in ALMACENAMIENTOS.items():
            vista.escribir(f"  {clave}. {descripcion}")
        eleccion = vista.pedir_texto("Elija un formato", "1")
        if eleccion in ALMACENAMIENTOS:
            _, constructor = ALMACENAMIENTOS[eleccion]
            return constructor()
        vista.escribir(f"  Opción no válida: {eleccion!r}. Las válidas son: "
                       f"{', '.join(ALMACENAMIENTOS)}.")


def _ubicacion_de(storage) -> str:
    """Devuelve la ruta donde un almacenamiento concreto guarda las partidas.

    Cada implementación guarda en un sitio distinto (un archivo o una
    carpeta), así que se le pregunta a cada una con el atributo que tenga. Se
    usa ``getattr`` con valor por defecto para no romper si algún día se añade
    un tercer formato con otra estructura.
    """
    ruta = getattr(storage, "ruta", None) or getattr(storage, "carpeta", None)
    return str(ruta) if ruta is not None else "(desconocido)"


def main() -> int:
    """Arranca la aplicación. Devuelve el código de salida del proceso.

    Devolver el código en vez de llamar a ``sys.exit`` dentro es lo que
    permite probar ``main()`` sin cerrar el intérprete en la prueba.
    """
    vista = PartidaView()
    try:
        storage = elegir_almacenamiento(vista)
    except OSError as error:
        # Si la carpeta de datos no se puede crear, no hay nada que hacer:
        # avisar y terminar es mejor que dejar una traza de error.
        vista.mostrar_error(f"no se pudo preparar la carpeta de datos ({error})")
        return 1

    # Se muestra dónde se va a guardar, para que quien juegue sepa dónde
    # buscar sus partidas y no se pierde por haber pulsado Enter sin leer.
    vista.mostrar_mensaje(f"  Las partidas se guardarán en: {_ubicacion_de(storage)}")
    # El controlador recibe sus tres colaboradores por el constructor. Esta es
    # toda la configuración del programa: si mañana se quiere jugar contra la
    # máquina, aquí se añadiría el motor como cuarto colaborador.
    controlador = PartidaController(vista=vista, storage=storage)
    try:
        controlador.ejecutar()
    except KeyboardInterrupt:
        # Ctrl+C es una forma de salir perfectamente legítima, y su traza de
        # error es un ruido que asusta a quien solo quería cerrar el programa.
        vista.escribir()
        vista.mostrar_mensaje("  Interrumpido. Hasta la próxima.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
