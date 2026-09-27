"""El puente entre un controlador que bloquea y una ventana que no puede.

Este es el problema que hace que "cambiar la vista" no sea solo escribir una
clase nueva, y conviene explicarlo sin rodeos.

El controlador está escrito como **código bloqueante**: pregunta
``vista.menu_inicio()`` y se queda parado hasta que alguien contesta. En una
consola eso es normal, porque el único hilo del programa puede esperar
tranquilamente.

``tkinter`` no puede. Su hilo principal dibuja la ventana y atiende los
clics, y **tocar un widget desde otro hilo hace que el programa se cuelgue o
reviente** (error "main thread is not in main loop" y cosas peores). Un
diálogo que espera con ``wait_window()`` en el hilo principal, además, impide
que ese hilo haga nada más mientras espera.

La solución es la de siempre en estos casos: el controlador se ejecuta en un
**hilo de trabajo** y la vista se encarga de traducir cada cosa que el
controlador pide. Todo el truco está en una frase: *quien manda a hacer el
trabajo en el hilo principal es la propia vista, no el controlador*.

Así, este archivo se queda deliberadamente pequeño: ejecuta el trabajo aparte y
le da a la vista **un solo dato**, ``en_hilo_principal()``, que es todo lo que
la vista necesita para saber si la llamada que recibe viene del hilo de la
interfaz o del de trabajo. Con esa respuesta, la vista encola con
``root.after`` cuando toca pintar, y encola y además espera cuando toca
preguntar.

Que el reparto viva en la vista y no aquí es lo que mantiene pequeño este
archivo, y tiene una ventaja: la vista es la que sabe qué llamadas pintan y
cuáles esperan. El puente no tiene por qué saber nada de menús ni de diálogos;
solo de hilos.

Por qué el puente está en ``views/`` y no en ``controllers/``: el hilo es un
problema *de la pantalla*. Si el controlador supiera de hilos, la consola
—que no quiere ninguno— pagaría las consecuencias. Aquí el controlador sigue
sin saber si hay uno, un hilo, o veinte.
"""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable


class PuenteHilos:
    """Ejecuta un controlador bloqueante aparte del hilo que dibuja la ventana.

    Uso típico::

        puente = PuenteHilos(controlador.ejecutar, al_terminar=root.destroy)
        puente.arrancar()
        root.mainloop()

    La vista consulta ``puente.en_hilo_principal()`` para saber si la
    llamada que recibe viene del hilo de la interfaz o del de trabajo, y a
    partir de ahí decide si la ejecuta, si la encola, o si la encola y espera.
    No hay ninguna otra diferencia entre los dos casos: el resto del código de
    la vista es idéntico, y esa es la propiedad que hace que este puente sea
    tan pequeño.
    """

    def __init__(
        self,
        trabajo: Callable[[], Any],
        al_terminar: Callable[[Any], None] | None = None,
        al_fallar: Callable[[BaseException], None] | None = None,
        nombre: str = "ajedrez-controlador",
    ) -> None:
        self.trabajo = trabajo
        self.al_terminar = al_terminar
        self.al_fallar = al_fallar
        self.nombre = nombre
        self._hilo: threading.Thread | None = None
        self._error: BaseException | None = None

    # ------------------------------------------------------------------
    # Arranque y estado
    # ------------------------------------------------------------------

    def arrancar(self) -> None:
        """Lanza el trabajo en su hilo. No se queda esperando: devuelve ya.

        Devolver ya es lo importante. Si esto esperase hasta el final, la
        ventana no llegaría nunca a pintarse, que es justo lo que se quiere
        evitar.
        """
        if self._hilo is not None:
            raise RuntimeError("El puente ya está arrancado; no se puede arrancar dos veces.")
        self._hilo = threading.Thread(target=self._envolver, name=self.nombre, daemon=True)
        self._hilo.start()

    def en_hilo_principal(self) -> bool:
        """True si quien llama es el hilo que puede tocar los widgets."""
        return threading.current_thread() is threading.main_thread()

    @property
    def vivo(self) -> bool:
        """True mientras el trabajo siga en marcha."""
        return self._hilo is not None and self._hilo.is_alive()

    def esperar(self, timeout: float | None = None) -> None:
        """Espera a que el trabajo termine. Solo para pruebas y para cerrar.

        En el programa normal nadie llama a esto: la ventana se cierra cuando
        el trabajo avisa con ``al_terminar``.
        """
        if self._hilo is not None:
            self._hilo.join(timeout)

    def _envolver(self) -> None:
        """Ejecuta el trabajo y avisa de cómo terminó.

        El trabajo va dentro de un ``try`` porque un hilo que muere con una
        excepción no se muere de forma limpia: el programa sigue con la ventana
        puesta y la partida a medias, sin que nadie sepa por qué. Aquí se
        recoge, se guarda y se avisa, que es lo único que permite entenderlo.
        """
        try:
            resultado = self.trabajo()
        except BaseException as error:  # noqa: BLE001 - se reenvía, no se oculta
            self._error = error
            if self.al_fallar is not None:
                self.al_fallar(error)
            else:
                traceback.print_exception(type(error), error, error.__traceback__)
            return
        if self.al_terminar is not None:
            self.al_terminar(resultado)
