# Ajedrez MVC

Ajedrez escrito en Python, con las reglas completas y sin ninguna dependencia
externa. El interés del proyecto no es el ajedrez: es la **arquitectura**, que
separa las reglas, los archivos y la pantalla en capas que se pueden probar por
separado, y que además permite cambiar de pantalla sin tocar las reglas.

```
main.py  /  main_gui.py          solo configuran y arrancan
        |
        v
   PartidaController              decide qué hacer
     |            |
     v            v
  la vista     BaseStorage      (el contrato de disco)
     |            |
     v            v
 PartidaView   JSONStorage
   VistaGUI      FENStorage
 (consola)      (fen)
     |
     v
  models/                        las reglas, y no saben nada de lo de arriba
```

## Puesta en marcha

No hay nada que instalar: solo la biblioteca estándar de Python.

```bash
python main.py
```

También hay una versión con ventana, con la misma partida y las mismas reglas:

```bash
python main_gui.py
```

Al arrancar se elige en qué formato se guardan las partidas (la decisión se
toma una vez, no en cada guardado, para no acabar con la misma partida
partida en dos sitios).

Para correr las pruebas:

```bash
python -m pytest
```

Y, si se quiere comprobar la ventana de verdad —que abre la ventana, dibuja el
tablero y contesta sola a los diálogos—:

```bash
python smoke_vista_gui.py
```

## Las dos vistas

Hay dos pantallas distintas, `PartidaView` (consola) y `VistaGUI` (ventana), y
el controlador no sabe cuál está usando: solo conoce el contrato
`InterfazVista` de `views/interfaz.py`. Por eso pasar de una a otra es cambiar
un argumento, y en ninguno de los dos casos hizo falta tocar el controlador.

Lo que hace posible el intercambio es que **las dos cumplen el mismo
`Protocol`**, sin heredar la una de la otra. Y el contrato está en `views/` y
no en `controllers/` porque describe lo que la vista *ofrece*, no lo que el
controlador *quiere*: así la dependencia va en un solo sentido.

Y hay un detalle que no es trivial. El controlador está escrito como código
**bloqueante**: pregunta `vista.menu_inicio()` y se queda parado hasta que
alguien contesta. En consola eso no estorba, porque el único hilo del programa
no tiene nada más que hacer. `tkinter` no puede hacerlo: su hilo principal
dibuja, y un diálogo que espera con `wait_window()` le impediría hacer nada más.

La solución es `views/hilo.py`: el controlador se ejecuta en un hilo aparte y
la vista traduce cada cosa que le piden. Pintar se encola con `root.after` y no
espera, para que el controlador siga avanzando; preguntar se encola y además
espera, con un `threading.Event`. Todo el reparto ocurre en un único método,
`VistaGUI._en_hilo_principal`, y por eso el resto de la vista es idéntico en los
dos casos.

La consecuencia de esto es que la versión con ventana **también bloquea**: sus
menús y preguntas son diálogos modales, y por eso se puede reutilizar el
controlador tal cual. Una ventana con botones de verdad, sin diálogos, exigiría
convertir el controlador en generadores; el punto exacto que habría que cambiar
son los **ocho** métodos de `InterfazVista` que esperan, y está marcado en el
código.

## Cómo se juega

Las jugadas se escriben con origen y destino pegados, y se aceptan en
cualquiera de estas formas:

```
e2e4      e2-e4      'e2 e4'      peón de e2 a e4
```

Si un peón llega a la última fila hay que indicar a qué pieza promociona:

```
a7a8q   q = dama   r = torre   b = alfil   n = caballo
```

Y hay una ayuda en la propia partida (**opción 8** del menú de juego) que
resume todo esto.

## Reglas implementadas

Todo el reglamento, salvo las variantes (ver más abajo):

- Movimiento de las seis piezas, con los bloqueos y las casillas que cada una
  ataca.
- **Promoción** a dama, torre, alfil o caballo, eligiendo explícitamente.
- **Enroque** corto y largo, con las cuatro condiciones: que el rey y la torre
  estén en su sitio, que las casillas intermedias estén vacías, que el rey no
  esté en jaque y que no pase por una casilla atacada.
- **Captura al paso**, tanto al generarla como al deducirla de un FEN.
- **Jaque, jaque mate y ahogado** (rey con casillas propias y sin salida legal).
- **Tablas** por cuatro vías: acuerdo, regla de las 50 jugadas sin capturas ni
  movimientos de peón, material insuficiente y repetición triple de la posición.
- **Abandono** y **deshacer** jugada.
- **Importación y exportación en FEN**, tanto el estándar de 6 campos como el
  corto de solo posición.

## Las dos capas de datos

El almacenamiento es intercambiable porque las dos implementaciones cumplen el
mismo contrato (`storage/base_storage.py`): `guardar`, `listar`, `cargar`,
`eliminar`, `existe`, `contar` y `listar_informes`.

| | JSON (por defecto) | FEN |
|---|---|---|
| Dónde | un solo archivo | un `.fen` por partida |
| Historial y notación | sí | no |
| Deshacer al recargar | sí | no |
| Estado final (mate, tablas) | se conserva | se recalcula |
| Formato estándar | no | sí |

La diferencia importa y conviene entenderla: **un FEN guarda la posición, no la
partida**. Se puede abrir en Lichess o chess.com y pegar en un foro, pero al
recargarlo no hay jugadas anteriores que mirar. El JSON es el formato por
defecto justo por eso; el FEN está para exportar.

Los errores de disco (permisos, carpeta llena, archivo corrupto) se capturan y
se traducen a un mensaje en vez de dejar una traza de error: no se puede
jugar por no poder guardar, pero tampoco hay por qué tumbar el programa.

## Estructura

```
main.py                     Configura y arranca. Nada más.
models/                     Las reglas. No saben qué es un menú ni un archivo.
  enums.py                  Color, TipoPieza, EstadoPartida.
  errores.py                Los errores del dominio.
  posicion.py               Una casilla: columna, fila y su notación (e4).
  pieza.py                  Una pieza y cómo se mueve.
  tablero.py                Las 64 casillas, los movimientos legales.
  partida.py                Una partida: turno, jaque, finales, FEN, historial.
storage/                    Lo único que toca el disco.
  base_storage.py           El contrato. Sin implementación.
  json_storage.py           Implementación en un archivo JSON.
  fen_storage.py            Implementación en archivos .fen.
views/
  interfaz.py               El contrato (Protocol) y las opciones de menú.
  partida_view.py           La consola.
  vista_gui.py              La ventana (tkinter). La segunda implementación.
  hilo.py                   El puente que la pone en marcha sin bloquearla.
controllers/
  partida_controller.py     Une las tres y decide qué hacer.
tests/                      353 pruebas.
```

La regla que sostiene el diseño: **el modelo no importa nada de las otras
capas**. `models/` no menciona archivos ni menús, y por eso se puede probar una
regla de ajedrez sin escribir nada en disco. Cambiar de formato de guardado es
cambiar una línea; cambiar la pantalla, otra.

## Pruebas

```bash
python -m pytest
```

Las pruebas de almacenamiento están **parametrizadas sobre los dos formatos**
(la misma batería, una vez contra JSON y otra contra FEN), que es la forma
barata de comprobar que la separación por contrato es real y no de palabra.

Las de la vista comprueban una promesa y no un resultado: que `PartidaView` y
`VistaGUI` tienen los mismos métodos públicos, y que una clase que le falte
uno se detecta como lo que es. La lista de métodos está escrita a mano en
`tests/test_interfaz.py`, a propósito: si alguien añade un método al contrato,
esa lista deja de cuadrar y hay que decidir qué vista lo implementa, en vez de
que se rompa más tarde en mitad de una partida.

Lo que la ventana no puede comprobarse sin pantalla, así que no está en la
batería: que dibuje el tablero y que un hilo de verdad la maneje. Eso está en
`smoke_vista_gui.py`, que se ejecuta a mano, abre la ventana y se contesta a
sí misma pulsando los botones de los diálogos. Esa prueba es la que destapó el
único fallo real de todo esto, y fue del arnés y no del programa.

## Limitaciones

- **No hay motor rival.** Se juega con un solo color contra uno mismo, pensado
  para practicar reglas. `main.py` señala dónde se añadiría un motor como
  cuarto colaborador del controlador.
- **Sin reloj** ni control de tiempo.
- **Sin variantes**: ni tres-tablas, ni rey a la isla, ni captura del rey.
- **Un solo jugador por partida**: no hay juego en red ni por turnos locales.
- La ventana usa **diálogos modales**, no botones: es lo que permite reutilizar
  el controlador sin reescribirlo, y el precio es que la partida no avanza
  mientras un menú está abierto.
- El menú de gestión de archivos no permite cambiar el formato con las partidas
  ya guardadas; el formato se elige al arrancar.
