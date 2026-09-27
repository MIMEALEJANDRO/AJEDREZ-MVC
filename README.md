# Ajedrez MVC

Ajedrez de consola escrito en Python, con las reglas completas y sin ninguna
dependencia externa. El interés del proyecto no es el ajedrez: es la
**arquitectura**, que separa las reglas, los archivos y la pantalla en capas
que se pueden probar por separado.

```
┌──────────────────────────────────────────────┐
│  main.py          solo configura y arranca    │
└───────────────────────┬──────────────────────┘
                        │
              ┌─────────▼─────────┐
              │  PartidaController │  decide qué hacer
              └────┬────────┬──────┘
        ┌──────────┘        └──────────┐
┌───────▼────────┐              ┌───────▼────────┐
│  PartidaView   │              │  BaseStorage   │
│  la pantalla   │              │  el contrato   │
└───────┬────────┘              └───────┬────────┘
        │                     ┌────────┴────────┐
┌───────▼────────┐      ┌──────▼──────┐  ┌──────▼───────┐
│  models/       │      │JSONStorage  │  │ FENStorage   │
│  las reglas    │      └─────────────┘  └──────────────┘
└────────────────┘
```

## Puesta en marcha

No hay nada que instalar: solo la biblioteca estándar de Python.

```bash
python main.py
```

Al arrancar se elige en qué formato se guardan las partidas (la decisión se
toma una vez, no en cada guardado, para no acabar con la misma partida
partida en dos sitios).

Para correr las pruebas:

```bash
python -m pytest
```

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
  partida_view.py           La consola. La única capa que habla con la persona.
controllers/
  partida_controller.py     Une las tres y decide qué hacer.
tests/                      337 pruebas.
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

## Limitaciones

- **No hay motor rival.** Se juega con un solo color contra uno mismo, pensado
  para practicar reglas. `main.py` señala dónde se añadiría un motor como
  cuarto colaborador del controlador.
- **Sin reloj** ni control de tiempo.
- **Sin variantes**: ni tres-tablas, ni rey a la isla, ni captura del rey.
- **Un solo jugador por partida**: no hay juego en red ni por turnos locales.
- El menú de gestión de archivos no permite cambiar el formato con las partidas
  ya guardadas; el formato se elige al arrancar.
