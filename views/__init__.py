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

Sobre el contrato: describe los seis métodos que el controlador le pide a la
pantalla, y ``SalidaDeConsola`` (en ``views/ventana.py``) los implementa todos,
así que se cumple de verdad y se comprueba con ``isinstance``. Cuando declaraba
diecisiete métodos —los de la consola y sus menús— era un contrato falso: la
única vista que había no lo cumplía. La explicación de por qué son seis está en
``views/interfaz.py``.

Lo que **no** cubre el contrato es el bucle de menús del controlador
(``ejecutar`` / ``jugar`` / ``gestionar_archivos``), que usa once métodos más que
ya no existen en ninguna pantalla. Sigue escrito y sigue probado, y es deuda
técnica aceptada: está el coste y el criterio de salida en el README, sección
"Deuda técnica aceptada".
"""

from views.interfaz import InterfazVista

__all__ = ["InterfazVista"]
