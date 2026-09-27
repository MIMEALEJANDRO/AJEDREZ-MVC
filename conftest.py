"""Configuración de ``pytest`` para el proyecto.

Al ejecutar ``pytest`` desde la raíz del proyecto, los paquetes del proyecto
(``models``, ``controllers``, ``storage``, ``views``) deben estar en el
``sys.path``. Pytest añade automáticamente al ``sys.path`` el directorio de
este archivo, que es la raíz del proyecto, de modo que los ``import`` absolutos
funcionan sin instalar nada ni usar rutas relativas.
"""
