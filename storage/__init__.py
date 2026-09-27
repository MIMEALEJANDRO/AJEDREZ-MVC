"""Capa de almacenamiento: lo único del programa que toca el disco.

Se separa del modelo por dos razones, y las dos son prácticas:

* Las reglas de ajedrez se pueden probar sin escribir archivos. Si
  ``Partida.mover`` guardara en disco, cada prueba dejaría basura en el
  proyecto.
* Cambiar de formato es cambiar una línea. ``JSONStorage`` y ``FENStorage``
  cumplen el mismo contrato, así que el controlador no cambia ni una línea al
  pasar de uno a otro.

Los módulos se leen en orden: primero el contrato (``base_storage``) y luego
las implementaciones, una por formato.

Importar desde este paquete es corto y esconde cuál de los dos se está
usando, que casi nunca es lo que importa en el código que llama.
"""

from storage.base_storage import BaseStorage
from storage.fen_storage import FENStorage
from storage.json_storage import JSONStorage

# Se exporta también la clase abstracta porque una prueba puede usarla para
# comprobar que las dos implementaciones cumplen el mismo contrato (por
# ejemplo, corriendo la misma batería de pruebas contra las dos).
__all__ = ["BaseStorage", "JSONStorage", "FENStorage"]
