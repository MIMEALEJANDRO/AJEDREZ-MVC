"""Capa de controlador: coordina modelo, vista y almacenamiento.

Importar desde este paquete hace que quien lo use no sepa todavía dónde vive
el controlador. Hoy solo hay uno, así que el atajo es una comodidad; el día
que haya un segundo controlador (uno para jugar contra la máquina, otro para
revisar una partida) el atajo se seguirá usando igual y cada uno se importará
por su módulo.
"""

from controllers.partida_controller import PartidaController

__all__ = ["PartidaController"]
