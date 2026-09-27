"""Prueba de humo de la ventana: la abre, la dibuja y contesta sola.

No comprueba que la ventana sea bonita ni que los botones estén en el sitio
justo. Comprueba lo que ``python main.py`` **no** puede comprobar: que la vista
se construye, pinta un tablero y contesta preguntas sin que nadie pulse nada.

Por eso hay dos partes:

* **En el hilo principal**, con la vista sin puente. Es el caso trivial.
* **Con un hilo de verdad**, que es el caso interesante: un ``PuenteHilos``
  arranca un trabajo en segundo plano y ese trabajo pinta y pregunta. El hilo
  principal solo atiende la ventana. Si esto funciona, la arquitectura
  funciona, porque es exactamente lo que hace ``main_gui.py``.

Las respuestas se pulsan solas con ``root.after``, pero se pulsan **los botones
de verdad**: se busca el ``Aceptar`` o el ``Cancelar`` del diálogo que hay
en pantalla y se invoca. Nada de Trucos ni de atajos por dentro.

No forma parte de la batería de pruebas: necesita pantalla y abre ventanas. Se
ejecuta a mano con ``python smoke_vista_gui.py``.
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from models.partida import Partida  # noqa: E402
from views.hilo import PuenteHilos  # noqa: E402
from views.vista_gui import VistaGUI  # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, descripcion: str) -> None:
    print(f"  {'OK   ' if condicion else 'FALLO'} {descripcion}")
    if not condicion:
        fallos.append(descripcion)


def buscar_boton(ventana: tk.Misc, texto: str) -> ttk.Button | None:
    """Busca un botón por su texto, recorriendo toda la ventana.

    Los diálogos anidan marcos (``marco`` y ``marco_botones``), así que hay que
    bajar en vez de mirar solo los hijos directos.
    """
    for hijo in ventana.winfo_children():
        if isinstance(hijo, ttk.Button) and str(hijo.cget("text")) == texto:
            return hijo
        encontrado = buscar_boton(hijo, texto)
        if encontrado is not None:
            return encontrado
    return None


# Los botones que el pulsador automático irá apretando, en orden.
textos: list[str] = []


def pulsar(root: tk.Tk, cada: int = 40) -> None:
    """Programa un pulsador automático: espera a que haya diálogo y lo acepta.

    Se vuelve a programar a sí mismo cada ``cada`` milisegundos porque los
    diálogos van apareciendo uno detrás de otro y hay que atenderlos por
    orden. Y se programa desde dentro del propio bucle de eventos, así que
    sigue funcionando mientras la vista está esperando con ``wait_window()``.
    """

    def intentar() -> None:
        if not textos:
            return
        for hijo in root.winfo_children():
            if isinstance(hijo, tk.Toplevel) and hijo.winfo_exists():
                boton = buscar_boton(hijo, textos[0])
                if boton is not None:
                    print(f"  (pulsando {textos[0]!r} en el diálogo)")
                    textos.pop(0)
                    boton.invoke()
                    break
        # Se vuelve a programar SIEMPRE, también después de pulsar. Los
        # diálogos vienen uno detrás de otro, y quien se quede sin programar
        # el siguiente turno deja al hilo de trabajo esperando para siempre.
        root.after(cada, intentar)

    root.after(cada, intentar)


def parte_sin_puente(root: tk.Tk, vista: VistaGUI) -> None:
    print("\n1) Sin puente, todo en el hilo principal")
    partida = Partida()
    partida.mover("e2", "e4")
    partida.mover("e7", "e5")

    vista.titulo("Partida en curso")
    vista.mostrar_tablero(partida)
    vista.mostrar_mensaje("Mensaje normal")
    vista.mostrar_error("no se pudo escribir en disco")
    vista.mostrar_ayuda()
    vista.mostrar_historial(partida)
    vista.mostrar_fen(partida)
    vista.mostrar_partidas(
        [{"id": "p1", "fecha": "2026-01-01", "resultado": "en curso", "nombre": "X"}]
    )
    vista.mostrar_partidas([])
    root.update()

    comprobar(vista.lienzo.find_all() != [], "el lienzo tiene algo dibujado")
    # 64 casillas + 64 números de fila + 16 letras de columna, y las piezas.
    comprobar(len(vista.lienzo.find_all()) >= 64, f"casillas y coordenadas dibujadas ({len(vista.lienzo.find_all())})")
    comprobar("En curso" in vista.etiqueta_estado.cget("text"), "la etiqueta de estado dice el estado")
    contenido = vista.texto.get("1.0", "end")
    comprobar("Mensaje normal" in contenido, "el mensaje se pintó")
    comprobar("no se pudo escribir en disco" in contenido, "el error se pintó")
    comprobar("1. e2-e4" in contenido, "el historial se pintó")
    comprobar("rnbqkbnr" in contenido, "el FEN se pintó")
    comprobar("no hay ninguna partida guardada" in contenido, "el listado vacío se avisó")


def parte_con_hilo(root: tk.Tk, vista: VistaGUI) -> None:
    print("\n2) Con hilo de verdad, como en main_gui.py")
    recibido: dict[str, object] = {}

    def trabajo() -> str:
        # Esto se ejecuta en el hilo de trabajo, no en el de la ventana.
        recibido["hilo"] = threading.current_thread().name
        partida = Partida()
        partida.mover("d2", "d4")
        vista.titulo("Partida en curso")
        vista.mostrar_tablero(partida)
        # Se pinta sin esperar: el controlador sigue avanzando.
        vista.mostrar_mensaje("El tablero se ha pintado desde el hilo de trabajo")
        # Y aquí se pregunta, que sí bloquea.
        recibido["nombre"] = vista.pedir_texto_opcional("¿Qué nombre le pones?")
        recibido["confirmado"] = vista.pedir_confirmacion("¿Lo guardo?")
        vista.mostrar_mensaje(f"nombre={recibido['nombre']!r} confirmado={recibido['confirmado']!r}")
        return "terminado"

    errores: list[BaseException] = []

    def al_terminar(resultado: object) -> None:
        # Igual que en ``main_gui.py``: el puente avisa desde el hilo de
        # trabajo, así que cerrar la ventana también se encola.
        root.after(0, cerrar, resultado, None)

    def al_fallar(error: BaseException) -> None:
        root.after(0, cerrar, None, error)

    def cerrar(resultado: object, error: BaseException | None) -> None:
        if error is not None:
            errores.append(error)
        else:
            recibido["resultado"] = resultado
        root.quit()

    # Red de seguridad: si algo se queda esperando para siempre, el bucle se
    # corta igualmente y la prueba lo dice en vez de colgarse.
    root.after(15000, lambda: recibido.setdefault("corte", "el bucle no salió solo"))

    puente = PuenteHilos(trabajo, al_terminar=al_terminar, al_fallar=al_fallar)
    vista.puente = puente

    # Cancelar el nombre (debe salir None, no ""), y aceptar la confirmación.
    textos.extend(["Cancelar", "Aceptar"])
    pulsar(root)

    puente.arrancar()
    # ``mainloop()`` de verdad, igual que el programa. No vale con
    # ``update()``: tkinter exige que el hilo principal esté *dentro* del bucle
    # de eventos para que un ``after`` encolado desde otro hilo sea aceptado.
    root.mainloop()
    root.update()

    comprobar(not errores, f"el trabajo no falló ({errores})")
    comprobar(recibido.get("hilo") != threading.main_thread().name, "el trabajo corrió en otro hilo")
    comprobar(recibido.get("resultado") == "terminado", "el puente avisó de que terminó")
    comprobar(recibido.get("nombre") is None, f"cancelar el nombre dio None (dio {recibido.get('nombre')!r})")
    comprobar(recibido.get("confirmado") is True, f"aceptar dio True (dio {recibido.get('confirmado')!r})")

    contenido = vista.texto.get("1.0", "end")
    comprobar(
        "pintado desde el hilo de trabajo" in contenido,
        "el mensaje pintado desde el otro hilo llegó a la ventana",
    )
    comprobar("nombre=None confirmado=True" in contenido, "el hilo de trabajo siguió después de preguntar")


def main() -> int:
    root = tk.Tk()
    root.withdraw()  # Se construye y se dibuja todo, sin molestar con la ventana.
    try:
        vista = VistaGUI(root)
        comprobar(vista.puente is None, "sin puente, la vista funciona sola")

        parte_sin_puente(root, vista)
        parte_con_hilo(root, vista)
    finally:
        root.destroy()

    print()
    if fallos:
        print(f"{len(fallos)} comprobaciones fallaron:")
        for una in fallos:
            print(f"  - {una}")
        return 1
    print("Todo correcto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
