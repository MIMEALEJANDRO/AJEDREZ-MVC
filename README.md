# Ajedrez MVC

Ajedrez escrito en Python, con las reglas completas y sin ninguna dependencia
externa. El interés del proyecto no es el ajedrez: es la **arquitectura**, que
separa las reglas, los archivos y la pantalla en capas que se pueden probar por
separado, y que además permite cambiar de pantalla sin tocar las reglas.

```
main.py  /  main_gui.py  /  main_ventana.py    solo configuran y arrancan
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
 (consola)        (fen)
  VentanaAjedrez
     |
     v
  models/                        las reglas, y no saben nada de lo de arriba
```

## Puesta en marcha

No hay nada que instalar: solo la biblioteca estándar de Python.

```bash
python main.py
```

También hay dos versiones con ventana, con la misma partida y las mismas reglas.
Una con menús:

```bash
python main_gui.py
```

Y otra con un tablero de verdad, sin menús: se hace clic en la casilla de origen
y en la de destino.

```bash
python main_ventana.py
```

Al arrancar se elige en qué formato se guardan las partidas (la decisión se
toma una vez, no en cada guardado, para no acabar con la misma partida
partida en dos sitios).

Para correr las pruebas:

```bash
python -m pytest
```

Y, si se quiere comprobar las ventanas de verdad —que abren la ventana, dibujan
el tablero y se contestan solas a los diálogos—:

```bash
python smoke_vista_gui.py   # la de menús
python smoke_ventana.py     # la de botones
```

## Las tres vistas

Hay tres pantallas distintas y el controlador no sabe cuál está usando. Lo
interesante es que **no lo sabe de la misma manera** en las tres, y que por eso
las dos formas de escrever el controlador se complementan en lugar de
competir.

### Dos vistas que cumplen el mismo contrato

`PartidaView` (consola) y `VistaGUI` (ventana con menús) cumplen las dos el
`Protocol` `InterfazVista` de `views/interfaz.py`, sin heredar la una de la
otra. Por eso pasar de una a otra es cambiar un argumento, y en ninguno de los
dos casos hizo falta tocar el controlador.

Lo que hace posible el intercambio es que **las dos cumplen el mismo
`Protocol`**, y el contrato está en `views/` y no en `controllers/` porque
describe lo que la vista *ofrece*, no lo que el controlador *quiere*: así la
dependencia va en un solo sentido.

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

La consecuencia de esto es que la versión con menús **también bloquea**: sus
menús y preguntas son diálogos modales, y por eso se puede reutilizar el
controlador tal cual. Una ventana con botones de verdad, sin diálogos, exigiría
convertir el controlador en generadores.

### Una vista que no cumple el contrato, a propósito

Esa limitación era exactamente el punto de partida de `views/ventana.py`
(`main_ventana.py`). Una ventana de ajedrez de verdad no tiene menús: tiene un
tablero, se hace clic en dos casillas y la jugada está hecha. **No hay nada que
preguntar.** Y si no hay nada que preguntar, el modelo de "el controlador
pregunta y espera" se queda sin usar, y con él se cae el `PuenteHilos` entero:
nadie espera, así que no hay nada que repartir entre el hilo que dibuja y el que
decide. Todo corre en el hilo principal de `tkinter`, que es lo correcto.

La relación se invierte. No es el controlador el que empuja menús hacia la
pantalla, es la pantalla la que **tira** de las acciones del controlador cuando
alguien pulsa un botón o hace clic en una casilla:

```
clic en e2, clic en e4   ->  controlador.aplicar_jugada("e2e4")
botón Deshacer           ->  controlador.deshacer()
botón Guardar            ->  controlador.guardar(...)
```

Esos métodos ya existían y ya estaban probados, porque son las acciones que el
menú de la consola llama por dentro. Lo único que faltaba era una puerta de
entrada para las jugadas, y esa es `PartidaController.aplicar_jugada`: la misma
validación, la misma traducción de errores y la misma comprobación de turno que
usa la consola, pero sin la pregunta previa. `introducir_jugada` se queda como
atajo de `aplicar_jugada(vista.pedir_jugada())` para las dos vistas que sí
preguntan.

Y `InterfazVista` se queda como estaba, cumpliendo su promesa de siempre. Esta
ventana **no** lo cumple, y es deliberado: no es intercambiable con las otras
dos —no se le puede poner un `PartidaView` debajo, ni al revés—, así que
declarar que lo cumpliría sería mentir, y un `Protocol` que miente es peor que
no tener contrato. Lo que sí comparte con el resto es lo que importa: `models/`
no sabe que esto existe, `storage/` tampoco, y el controlador no ha tenido que
cambiar de forma para acomodar a una tercera pantalla. La diferencia entre una
ventana con menús y una con botones está entera en la vista, que es donde
debería estar.

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
main.py                     Configura y arranca (consola). Nada más.
main_gui.py                 Configura y arranca (ventana con menús).
main_ventana.py             Configura y arranca (ventana con botones).
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
  partida_view.py           La consola. Cumple el contrato.
  vista_gui.py              La ventana de menús (tkinter). Cumple el contrato.
  hilo.py                   El puente que la pone en marcha sin bloquearla.
  ventana.py                La ventana jugable, de botones. No cumple el contrato.
controllers/
  partida_controller.py     Une las tres y decide qué hacer.
tests/                      636 pruebas.
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

Lo que las ventanas no pueden comprobarse sin pantalla, así que no está en la
batería: que dibujen el tablero y que un hilo de verdad maneje una de ellas.
Eso está en `smoke_vista_gui.py` y en `smoke_ventana.py`, que se ejecutan a
mano, abren la ventana y se contestan a sí mismas. La segunda apareció porque
la primera destapó el único fallo real de todo esto, y fue del arnés y no del
programa.

Lo que sí entra en la batería, y con 658 pruebas, es lo que la ventana jugable
sí tiene detrás: el **mapeo de píxeles a casillas**. Es lo único que la
ventana calcula por su cuenta y lo único que un fallo hace que parezca un
fallo de las reglas, así que se comprueba entero y sin pantalla: dónde cae
cada una de las 64 casillas, que deshacer ese cálculo devuelva la casilla de
partida, y que el recorrido que pintan, el que pinta el ratón y el que
responde al clic **sean el mismo objeto y no tres copias**. Ese último caso es
el que importa: si cada uno calculara su propia cuenta, bastaría con invertir
una fila en uno de los dos para que se clicaran casillas distintas de las que
se ven.

## Rendimiento y límites conocidos

Esta sección existe para que nadie descubra por sorpresa hasta dónde escala el
motor. Las cifras son de un `perft(3)` con Python 3.14 en un portátil corriente,
y se miden con `python perft_ajedrez.py --profundidad 3`.

### Qué es el perft y por qué es la medida

`perft(n)` cuenta cuántas rutas de `n` jugadas legales hay desde una posición. No
es un test de rendimiento "normal": es la medida más dura que hay, porque obliga
a que la generación de jugadas sea correcta en todos los casos a la vez (jaque,
enroque, captura al paso, promoción) y a que además sea rápida. Si el número
cuadra y tarda lo que tarda, las reglas están bien.

### Antes y después

El cuello de botella era `Tablero.es_legal()`: clonaba el tablero entero y
recalculaba **todas** las casillas atacadas por el rival, una vez por cada jugada
candidata. Eso convertía `movimientos_legales()` en algo del orden de
O(piezas²) por posición, sin ningún cacheo.

| Posición | perft(3) antes | perft(3) ahora | Mejora |
|---|---|---|---|
| Inicial | 3,6 s | 1,3 s | 2,8x |
| Kiwipete | 69,3 s | 24,0 s | 2,9x |
| Al paso | 0,8 s | 0,3 s | 2,7x |
| Promoción | 5,2 s | 1,8 s | 2,9x |
| Enroque mixto | 32,0 s | 13,3 s | 2,4x |
| Jaque | 24,5 s | 9,8 s | 2,5x |
| **Suma de los seis** | **135,4 s** | **50,5 s** | **2,7x** |

### Qué se hizo, y qué no

Dos cosas, en este orden:

1. **Análisis de clavadas por posición** (`_preparar_legalidad`). En vez de
   clonar por candidata, se calcula una vez: qué casillas ataca el rival, si
   estamos en jaque y qué piezas propias están **clavadas** (son el único bloqueo
   entre el rey y una pieza rival que resbala). Una pieza que no está clavada se
   puede declarar legal sin clonar nada, porque al moverla no puede aparecer un
   ataque nuevo contra el rey. Se sigue simulando con clon, correctamente, todo
   lo que no se puede decidir así: el movimiento del rey, las jugadas con jaque,
   el enroque y la captura al paso (que es la única capaz de descubrir un ataque
   por una línea que no pasa por la pieza que se mueve).
2. **`Posicion` más barata** (`slots`, un `__hash__` que no construye tuplas y un
   catálogo de las 64 casillas reutilizado en `desplazar`). No cambia la
   representación del tablero ni una sola regla: `Posicion` era la pieza de datos
   más caliente y se creaba y se hasheaba millones de veces por perft.

`python -m pytest` tarda 6,2 s con 658 pruebas (antes: 636 en 4,9 s).

### Dónde está el límite ahora, y qué NO se ha hecho

Después de estos cambios, el 48% del tiempo que queda está en un solo sitio:
`Tablero.clonar()`. La simulación de una jugada clona el tablero entero, y eso
significa crear unos 32 objetos `Pieza` nuevos y validarlos uno a uno, miles de
veces. La cifra sale de `cProfile`, que infla un poco el coste de las llamadas a
función, así que en tiempo real es algo menor: pero es el número más grande de la
lista, y no es una sospecha.

**No se ha cambiado la representación del tablero** (sigue siendo un diccionario
`Posicion -> Pieza`) a propósito, y la razón está en el perfil: el diccionario y
el *hashing* de casillas son hoy una fracción pequeña del coste, mientras que
`clonar` es la mitad. Convertir el tablero en un array plano de 64 casillas
eliminaría el *hashing*, que ya no es el problema, y **no** tocaría `clonar`, que
sí lo es. Sería reescribir el módulo para no ganar casi nada.

Lo que sí merece la pena, como paso aparte y con su propia medición, es
atacar `clonar`, y hay dos caminos:

- **Que `Pieza` sea inmutable** (hoy nadie la muta: se comprueba) y que `clonar`
  comparta los mismos objetos en vez de copiarlos. Es el cambio más pequeño y el
  que más rinde, porque elimina de raíz la creación de las 600 000 piezas por
  perft(3). Toca una clase pública, así que no se ha hecho sin preguntar.
- **Aplicar y desaplicar** (hacer la jugada y deshacerla en el mismo tablero, en
  vez de clonar) es lo que hacen los motores de verdad, y elimina el coste por
  completo. Es más delicado: hay que devolver el tablero **exactamente** como
  estaba, derechos de enroque y última jugada incluidos, y un error ahí no se ve
  en un perft corto.

### Para qué sirve hoy

- **Jugar entre dos personas**: de sobra. Generar las jugadas de una posición es
  instantáneo, y la partida va sin tirones.
- **Analizar una partida o un final**: de sobra. Recorrer unos cientos de miles
  de posiciones entra holgadamente.
- **Un rival con búsqueda (minimax, alfa-beta)**: todavía **no**. Un perft(3) de
  Kiwipete son 24 s, y una búsqueda de 3-4 niveles visita millones de posiciones.
  Con estas cifras haría falta además **tablas de transposición** (guardar el
  resultado de las posiciones ya visitadas, que aquí no hay ninguna) y probablemente
  el trabajo sobre `clonar` del punto anterior. Es un trabajo de otra vez, no un
  ajuste.

En otras palabras: el generador de jugadas ya no es el problema. Lo que falta
para una IA es la búsqueda y su cacheo, no más velocidad de generación.

## Limitaciones

- **No hay motor rival.** Se juega con un solo color contra uno mismo, pensado
  para practicar reglas. `main.py` señala dónde se añadiría un motor como
  cuarto colaborador del controlador.
- **Sin reloj** ni control de tiempo.
- **Sin variantes**: ni tres-tablas, ni rey a la isla, ni captura del rey.
- **Un solo jugador por partida**: no hay juego en red ni por turnos locales.
- La ventana de menús usa **diálogos modales**, no botones: es lo que permite
  reutilizar el controlador sin reescribirlo, y el precio es que la partida no
  avanza mientras un menú está abierto. La ventana de botones no paga ese
  precio, porque no usa el contrato; a cambio, no es intercambiable con las
  otras dos vistas.
- El menú de gestión de archivos no permite cambiar el formato con las partidas
  ya guardadas; el formato se elige al arrancar.
