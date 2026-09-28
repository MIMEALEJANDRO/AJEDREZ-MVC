"""Capa de vista: la presentación, en ventana.

Hay una vista y un contrato:

* ``VentanaAjedrez`` — el tablero jugable de ``tkinter``, en ``views.ventana``.
* ``InterfazVista`` — el contrato que describe qué necesita el controlador de
  una pantalla.

De aquí solo se exporta el contrato. La ventana **no** se exporta a propósito:
importarla carga ``tkinter``, y entonces cualquier ``import views`` —el de las
pruebas del modelo, o el de un módulo que no dibuja nada— necesita que tkinter
esté instalado. Que se importe solo quien la va a usar
(``from views.ventana import VentanaAjedrez``) mantiene el resto del programa sin
esa dependencia.

Sobre el contrato, y conviene ser claro: desde que se borraron la consola y la
ventana de menús, ``InterfazVista`` **no lo implementa ninguna pantalla**, porque
``VentanaAjedrez`` no usa menús (eso se explica en su propio módulo, y es a
propósito). Se conserva igualmente por dos razones, ambas deliberadas:

* el bucle de menús del controlador (``ejecutar`` / ``jugar`` /
  ``gestionar_archivos``) sigue escrito y sigue probado contra el contrato, así
  que borrarlo sería borrar el andamiaje de esas pruebas;
* las tablas ``OPCIONES_INICIO`` / ``OPCIONES_PARTIDA`` / ``OPCIONES_ARCHIVO``
  viven en el mismo módulo y son los datos de esos menús.

Que sobre código sin usar es una poda pendiente, no un olvido. Está anotado en
el README, en "Qué queda sin usar y por qué", junto con la propuesta de podarlo.
"""

from views.interfaz import InterfazVista

__all__ = ["InterfazVista"]
