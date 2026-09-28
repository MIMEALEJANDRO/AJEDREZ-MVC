# Ajedrez MVC

Ajedrez escrito en Python, con las reglas completas y sin ninguna dependencia
externa. El interés del proyecto no es el ajedrez: es la **arquitectura**, que
separa las reglas, los archivos y la pantalla en capas que se pueden probar por
separado, y que además permite cambiar de pantalla sin tocar las reglas.

```
main_ventana.py                      solo configura y arranca
        |
        v
   PartidaController                  decide qué hacer
        |
        v
  VentanaAjedrez                     dibuja y recoge los clics
        |
        v
   models/                           las reglas, y no saben nada de lo de arriba
        |
storage/json_storage.py              el disco (JSON)
```

`views/interfaz.py` (el contrato `InterfazVista`) y el bucle de menús del
controlador siguen en el código, pero **ninguna pantalla los usa ya**. Está
explicado en [Qué queda sin usar y por qué](#qué-queda-sin-usar-y-por-qué).


## Puesta en marcha

No hay nada que instalar: solo la biblioteca estándar de Python.

```bash
python main_ventana.py
```

Esa es **la única** forma de arrancar. Se hace clic en la casilla de origen y en
la de destino, y la jugada está hecha: no hay menús.

Las partidas se guardan en `data/partidas.json`. **Ya no se pregunta el formato
al arrancar**: antes se ofrecía JSON o FEN con un diálogo, y con la consola y la
ventana de menús fuera no hay a quién darle la elección. Se queda el JSON, que es
el único formato que guarda el historial y por tanto el único que permite
deshacer. `storage/fen_storage.py` y `FENStorage` **se conservan y se prueban**:
siguen sirviendo para exportar una posición a otro programa, aunque la ventana ya
no los ofrezca.

Para correr las pruebas:

```bash
python -m pytest
```

Y, si se quiere comprobar la ventana de verdad —que la abre, dibuja el tablero y
se contesta sola a los clics—:

```bash
python smoke_ventana.py
```

`smoke_ventana.py` no forma parte de la batería de pytest porque necesita
pantalla; en Linux sin pantalla se puede lanzar con `xvfb-run -a`.

## La vista y el contrato

Antes había tres pantallas y el controlador no sabía cuál estaba usando. Ahora
hay **una**, y conviene explicar qué se perdió y qué se conservó, porque el
cambio no es solo "borrar archivos".

### Lo que había: dos vistas con menús y un hilo

`PartidaView` (consola) y `VistaGUI` (ventana con menús) cumplían las dos el
`Protocol` `InterfazVista` de `views/interfaz.py`, sin heredar la una de la
otra. Por eso pasar de una a otra era cambiar un argumento, y en ninguno de los
dos casos hizo falta tocar el controlador.

Había además un detalle de hilo, que era lo caro de aquel diseño. El controlador
está escrito como código **bloqueante**: pregunta `vista.menu_inicio()` y se
queda parado hasta que alguien contesta. En consola eso no estorba, porque el
único hilo del programa no tiene nada más que hacer. `tkinter` no puede hacerlo:
su hilo principal dibuja, y un diálogo que espera con `wait_window()` le impediría
hacer nada más.

La solución era `views/hilo.py`: el controlador se ejecutaba en un hilo aparte y
la vista traducía cada cosa que le pedían. Pintar se encolaba con `root.after` y
no esperaba, para que el controlador siguiera avanzando; preguntar se encolaba y
además esperaba, con un `threading.Event`. Todo el reparto vivía en un único
método, `VistaGUI._en_hilo_principal`.

Ese diseño tenía un punto flojo documentado en el propio módulo, y era este: la
vista leía `partida.tablero` desde el hilo principal mientras el controlador lo
mutaba desde el de trabajo, sin ningún cerrojo. Funcionaba porque el GIL y porque
cada turno acababa bloqueando en un menú, no porque estuviera protegido. Con un
rival que calculase en segundo plano se habría roto de verdad. Borrar las dos
vistas con menús elimina ese problema entero, no lo silencia.

### Lo que hay: una vista que no cumple el contrato, a propósito

`views/ventana.py` es la pantalla que quedó, y **no** implementa `InterfazVista`.
Una ventana de ajedrez de verdad no tiene menús: tiene un tablero, se hace clic en
dos casillas y la jugada está hecha. **No hay nada que preguntar.** Y si no hay
nada que preguntar, no hace falta ni puente de hilos: nadie espera, así que no hay
nada que repartir entre el hilo que dibuja y el que decide. Todo corre en el hilo
principal de `tkinter`, que es lo correcto.

La relación se invierte. No es el controlador el que empuja menús hacia la
pantalla, es la pantalla la que **tira** de las acciones del controlador cuando
alguien pulsa un botón o hace clic en una casilla:

```
clic en e2, clic en e4   ->  controlador.aplicar_jugada("e2e4")
botón Deshacer           ->  controlador.deshacer()
botón Guardar            ->  controlador.guardar(...)
```

Esos métodos ya existían y ya estaban probados, porque son las acciones que el
menú de la consola llamaba por dentro. Lo único que faltaba era una puerta de
entrada para las jugadas, y esa es `PartidaController.aplicar_jugada`: la misma
validación, la misma traducción de errores y la misma comprobación de turno, pero
sin la pregunta previa. `introducir_jugada` se queda como atajo de
`aplicar_jugada(vista.pedir_jugada())` para el bucle de menús.

Lo que sí comparte con el resto es lo que importa: `models/` no sabe que esto
existe, `storage/` tampoco, y el controlador no ha tenido que cambiar de forma
para acomodar la pantalla.

### Qué queda sin usar y por qué

Borrar las dos vistas con menús deja código que ya no ejecuta nadie. Se conserva,
y se apunta aquí para que quede como decisión y no como descuido:

| Qué | Por qué se queda |
|---|---|
| `InterfazVista` (`views/interfaz.py`) | El bucle de menús del controlador está escrito y probado contra él. Si se borrara el contrato, se caerían sus pruebas. |
| `OPCIONES_INICIO` / `OPCIONES_PARTIDA` / `OPCIONES_ARCHIVO` | Son los datos de esos menús, y viven en el mismo módulo. |
| `ejecutar` / `jugar` / `gestionar_archivos` del controlador | Mismo motivo: sus pruebas siguen en pie y documentan cómo se conversa con una persona. |
| `introducir_jugada` | Atajo de `aplicar_jugada` para el bucle de menús. |
| `FENStorage` | Formato estándar para exportar a otro programa. Ya no se ofrece en la ventana, pero se prueba. |

**Propuesta de poda** (no aplicada, porque es una decisión de alcance y no un
detalle): si el proyecto ya no va a recuperar los menús, todo lo de la tabla
anterior se puede ir en un solo commit —`views/interfaz.py` entero, el bucle de
menús del controlador y `tests/test_controlador.py` con lo que lo prueba—, y el
proyecto quedaría con una sola forma de hablar con la persona. El precio sería
perder unas 70 pruebas que hoy vigilan la traducción de errores y el guardado, así
que **no lo he hecho**: no es una limpieza, es un recorte de funcionalidad, y
decide quien lleva el proyecto.


## Cómo se juega

En la ventana se juega con el ratón: se hace clic en la casilla de origen y en
la de destino. El panel lateral dice siempre cuál fue la última jugada
("Blancas e2-e4"), y el tablero se ilumina solo cuando le toca a quien está
jugando y se atenúa cuando no.

Lo demás —el FEN y el historial completo— está detrás del botón **Mostrar FEN**,
que los despliega y los vuelve a recoger. Antes estaban siempre a la vista, que
es mucha información para lo que se quiere de verdad al mover una pieza.

Para elegir bando, el selector **Juegas con:** del panel. Con "Blancas" o
"Negras" el tablero se gira para tener tus piezas abajo y **empieza ese bando**;
con "Los dos colores" no hay bando y se juega la partida entera. Cambiar de bando
con la partida ya empezada pregunta antes de reiniciarla.

Y hay una ayuda en la propia partida (**opción 8** del menú de juego) que
resume las notaciones. Ese menú es del bucle antiguo de la consola y **no lo
ofrece la ventana**: la nota está en [Qué queda sin usar](#qué-queda-sin-usar-y-por-qué).

El bucle de menús también acepta la jugada escrita a mano:
```
e2e4      e2-e4      'e2 e4'      peón de e2 a e4
```

Y si un peón llega a la última fila hay que indicar a qué pieza promociona:

```
a7a8q   q = dama   r = torre   b = alfil   n = caballo
```

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
main_ventana.py             Configura y arranca. Nada más.
models/                     Las reglas. No saben qué es un menú ni un archivo.
  enums.py                  Color, TipoPieza, EstadoPartida.
  errores.py                Los errores del dominio.
  posicion.py               Una casilla: columna, fila y su notación (e4).
  pieza.py                  Una pieza y cómo se mueve.
  tablero.py                Las 64 casillas, los movimientos legales.
  partida.py                Una partida: turno, jaque, finales, FEN, historial.
storage/                    Lo único que toca el disco.
  base_storage.py           El contrato. Sin implementación.
  json_storage.py           Implementación en un archivo JSON. La que usa la ventana.
  fen_storage.py            Implementación en archivos .fen. Se conserva, no se ofrece.
views/
  interfaz.py               El contrato (Protocol) y las opciones de menú.
                            Sin pantalla que lo cumpla: ver "Qué queda sin usar".
  ventana.py                La ventana jugable, de botones. No cumple el contrato.
controllers/
  partida_controller.py     Une las tres y decide qué hacer.
tests/                      626 pruebas.
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

Las del controlador comprueban la coordinación con dobles: una vista que
registra lo escrito y un almacenamiento en memoria, así que ni la consola ni el
disco entran en juego. Entre ellas siguen las que verifican que los menús no
dejan huecos en la numeración y que la ayuda es siempre la opción 8: esos datos
viven en `views/interfaz.py` y se han conservado aunque las vistas se fueran
(ver "Qué queda sin usar").

Lo que la ventana no puede comprobarse sin pantalla, así que no está en la
batería: que dibuje el tablero y que un clic mueva la pieza correcta. Eso está
en `smoke_ventana.py`, que se ejecuta a mano, abre la ventana y se contesta a sí
misma. En un equipo sin pantalla se puede lanzar con `xvfb-run -a
python smoke_ventana.py`, que es como lo ejecuta la CI.

Lo que sí entra en la batería, y con 626 pruebas, es lo que la ventana jugable
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
  para practicar reglas. `main_ventana.py` señala dónde se añadiría un motor como
  cuarto colaborador del controlador.
- **Sin reloj** ni control de tiempo.
- **Sin variantes**: ni tres-tablas, ni rey a la isla, ni captura del rey.
- **Un solo jugador por partida**: no hay juego en red ni por turnos locales.
- **Solo se guarda en JSON.** `FENStorage` sigue existiendo y probado, pero la
  ventana no lo ofrece: el formato se decide en el arranque, sin preguntar.
- **Sin consola.** No hay forma de jugar en modo texto. Es una pérdida real de
  comodidad para depurar y para jugar en una máquina sin escritorio gráfico, y se
  aceptó a conciencia al dejar una sola forma de arrancar. Si vuelve a hacer
  falta, `PartidaController.aplicar_jugada` y compañía son la puerta: una
  `PartidaView` nueva no tocaría ni las reglas ni el controlador.
- **Jugar con un solo bando, sin rival, solo deja hacer una de cada dos jugadas.**
  Es el comportamiento que fija `color_jugador`: si juegas con negras, el
  controlador no te deja mover las blancas, así que después de tu jugada el
  turno se te escapa hasta la siguiente. Para practicar está el modo "Los dos
  colores", que es el único en el que se juega una partida entera. **Aviso, sin
  cambios aplicados**: el selector arranca en "Blancas", y para una aplicación
  cuyo fin es practicar reglas eso es un mal punto de partida. Lo razonable sería
  arrancar en "Los dos colores" (una línea) o pedir el bando al empezar, pero es
  una decisión de uso y no la he tomado por mi cuenta.
- Queda código sin uso tras borrar las vistas con menús (el contrato y el bucle
  de menús del controlador). Ver [Qué queda sin usar y por qué](#qué-queda-sin-usar-y-por-qué).

