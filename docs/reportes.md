# Cómo leer los reportes

Cada corrida escribe sus reportes en `<corrida>/reports/` (los genera
`scripts/report.py` al terminar `make cts` o `make route`, o con
`make report`):

| Archivo      | Lo escribe          | Contenido |
| :----------- | :------------------ | :-------- |
| `qor.md`     | `cts` y `route`     | Resumen de la corrida |
| `cts.md`     | `cts` y `route`     | El árbol de clock |
| `routing.md` | solo `route`        | Routing global, antenas, routing detallado y chequeos |
| `timing.md`  | `cts` y `route`     | Timing en cada etapa, esquinas y caminos críticos |

Este documento explica cada tabla: qué es cada fila y cada columna. Los
números de ejemplo son los de la corrida de referencia
(`rt_ref_2026-10-28_17-24-31`); los tuyos van a ser parecidos, pero no
iguales.

Unidades: tiempos en **ns**, largos en **µm**, capacidades en **pF**,
potencia en **mW**.

---

## 0. El encabezado (todos los reportes)

Todos los reportes empiezan con la misma tabla, para saber de dónde salen
los datos:

| Fila | Qué es |
| :--- | :----- |
| `Run` | El nombre de esta corrida (el directorio en `designs/ibex/runs/`). `cts_...` si se corrió `make cts`, `rt_...` si se corrió `make route`. |
| `Placement from TP2 run` | La corrida del TP2 que importaste con `make import-tp2`: de ahí sale el layout de partida. |
| `Netlist from TP1 run` | La corrida del TP1 de la que salió el netlist que usó ese placement. |
| `Std cell library` | La biblioteca de celdas estándar (`sky130_fd_sc_hd`, la misma de los TP anteriores). |
| `Clock` | El puerto de clock y su período: `clk_i @ 100 ns (10.0 MHz)`. |

---

## 1. `qor.md`: resumen

*QoR* (*quality of results*): los números principales de la corrida.

### Tabla de métricas

| Fila | Qué es |
| :--- | :----- |
| `Std cell instances` | Cuántas celdas estándar tiene el diseño (sin contar las celdas de relleno, que se cuentan aparte en `routing.md`). Incluye los buffers que agregó CTS y los diodos de antena del routing: por eso es mayor que en el TP2, y en una corrida `rt_` es mayor que en una `cts_`. |
| `Std cell area (µm²)` | La suma del área de esas celdas. |
| `Clock-class cells (tree, delay buffers and dummy loads)` | Cuántas celdas son de tipo "buffer o inversor de clock" (`clkbuf`, `clkinv`, ...): la gran mayoría son las que agregó CTS (ver `cts.md`). Se cuenta por tipo de celda, así que si alguna celda de ese tipo se usa fuera del árbol, también se suma. |
| `Wirelength, HPWL after TP2 placement (µm)` | El largo de cables **estimado** al final del TP2: la suma, para cada net, del semiperímetro del rectángulo que encierra sus pines (*half-perimeter wirelength*). |
| `Wirelength after global routing (µm)` | El largo según el routing global (sección 3.1). Solo en corridas `rt_`. |
| `Wirelength after detailed routing (µm)` | El largo **real** de los cables dibujados por el routing detallado. Solo en corridas `rt_`. |
| `Vias` | Cuántas vías (conexiones entre dos capas de metal) hay en el layout final. |
| `DRC violations after detailed routing` | Violaciones de reglas de diseño (cables demasiado cerca, superpuestos, ...) que quedaron al final. Tiene que ser 0. |
| `Antenna violations (nets)` | Nets que siguen teniendo violaciones de antena al final (sección 3.2). |

En una corrida `cts_` las filas de routing no aparecen, y al final dice
`Routing: not run (use make route)`.

### `Timing at each stage`

Es la misma tabla que la primera de `timing.md`: está explicada en la
sección 4.1.

---

## 2. `cts.md`: el árbol de clock

### 2.1 `Clock nets found`

Los nets de clock que encontró CTS **antes** de construir el árbol, y cuántos
pines de clock (*sinks*) maneja cada uno.

| Columna | Qué es |
| :------ | :----- |
| `Clock net` | El nombre del net. |
| `Sinks` | Cuántos pines de clock (de flip-flops, de las SRAM o del clock gate) cuelgan de ese net. |

Las filas, en el Ibex:

| Fila | Qué es |
| :--- | :----- |
| `clk_i` | El clock que entra por el pin del chip. Llega sin pasar por el clock gate a las 6 SRAM (2 pines cada una: `clk0` y `clk1`) y al clock gate: 13 sinks. |
| `clk_i_regs` | CTS separa los flip-flops que cuelgan directamente de `clk_i` (sin pasar por el clock gate) en un net aparte. En el Ibex hay uno solo. |
| `clk` | La salida del clock gate (`core_clock_gate_i`): el clock de todo el core, que llega a los 2351 flip-flops. En el TP2 este net lo manejaba una sola celda. |

### 2.2 `Clock tree`: un árbol por net

| Columna | Qué es |
| :------ | :----- |
| `Clock net` | La raíz del árbol. |
| `Sinks` | Cuántas hojas tiene el árbol ya construido. Puede ser mayor que en la tabla anterior porque incluye las *dummy loads* (abajo): en `clk`, 2547 = 2351 flip-flops + 196 dummies. |
| `Leaf buffers` | Los buffers del último nivel, los que manejan directamente los flip-flops. |
| `Path depth` | Cuántos buffers hay entre la raíz y una hoja: el mínimo y el máximo (por ejemplo `4 - 5`). |
| `Avg. sink wire length (µm)` | El largo promedio del cable de clock desde la raíz hasta cada hoja. El de `clk_i` es grande porque las SRAM están en los bordes del chip. |
| `Dummy loads` | Celdas que no hacen nada lógico: CTS las agrega solo como **carga** en las ramas más livianas, para que tarden lo mismo que las más cargadas. |

`clk_i_regs` no aparece porque con un solo sink no hace falta árbol.

### 2.3 La tabla de celdas

| Fila | Qué es |
| :--- | :----- |
| `Clock buffers inserted` | Total de buffers que agregó CTS para armar el árbol. |
| `Delay buffers (latency balancing)` | Buffers que no hacen falta para manejar la carga: se agregan solo para **retrasar** una rama que llegaba demasiado temprano, así su latencia se parece a la del resto. |
| `Cell used: <celda>` | Cuántos buffers del árbol son de cada tipo. `clkbuf_16` es más fuerte (maneja más carga) que `clkbuf_8`. |
| `Dummy load: <celda>` | Cuántas *dummy loads* de cada tipo se agregaron. |

### 2.4 `Clock latency and skew after CTS`

Es la salida textual de `report_clock_latency` de OpenSTA, en el STA que
corre justo después de CTS (paso 02). Ejemplo:

```
Clock clk
rise -> rise
    min     max
0.000000 0.000000 source latency
1.051102         network latency _27391_/CLK
        1.449392 network latency _25369_/CLK
---------------
1.051102 1.449392 latency
        0.398289 skew
```

- `Clock clk`: el clock del SDC (definido sobre el puerto `clk_i`). Abarca a
  todos los sinks, pasen o no por el clock gate.
- `rise -> rise`: el flanco de **subida** en `clk_i`, llegando como flanco
  de subida a cada sink. Es el flanco en que capturan los flip-flops: es la
  sección que importa.
- `fall -> fall`: lo mismo con el flanco de **bajada**. Los flip-flops no
  lo usan para capturar, pero las SRAM sí trabajan con él.
- Columnas `min` y `max`: el sink al que el clock llega **primero** y al que
  llega **último**.
- `source latency`: retardo **antes** del pin `clk_i` (un oscilador, un PLL
  externo). Acá no se modela: es 0.
- `network latency`: retardo **dentro** del chip, desde `clk_i` hasta el pin
  de clock, a través de los buffers y cables del árbol. Al lado figura el pin
  donde se da el mínimo o el máximo.
- `latency`: source + network.
- `skew`: max − min. Cuánto se desfasa el clock entre el sink más temprano y
  el más tardío.

Solo compara dos pines, los extremos: no dice cómo se reparten los demás
(para eso, el Clock Tree Viewer de la GUI).

### 2.5 `Timing repair after CTS`

Después de CTS, LibreLane intenta reparar las violaciones de timing que haya
creado el árbol (paso 03).

| Fila | Qué es |
| :--- | :----- |
| `Setup` | `no violations` si no había nada que reparar en setup; si no, cuántos buffers agregó. |
| `Hold` | `no violations`, o cuántos caminos violaban hold y cuántos *hold buffers* (buffers que retrasan un camino demasiado rápido) insertó. |

### 2.6 `Power`

La potencia estimada del diseño en la esquina `tt`, en el **último** STA de
la corrida (el final en una corrida `rt_`, el paso 04 en una `cts_`).

| Fila | Qué es |
| :--- | :----- |
| `Sequential` | Flip-flops y latches. |
| `Combinational` | La lógica combinacional (compuertas, buffers de señal). |
| `Clock` | El árbol de clock: los buffers de clock y la carga de los pines de clock. |
| `Macro` | Las SRAM. |
| `Total` | La suma. |

| Columna | Qué es |
| :------ | :----- |
| `Power (mW)` | Potencia de ese grupo (dinámica por conmutación más estática por fugas), con una actividad de conmutación supuesta por la herramienta, no medida. |
| `Share` | Porcentaje del total. |

---

## 3. `routing.md`: el routing (solo `make route`)

### 3.1 `Global routing`

El routing global no dibuja cables: divide el chip en una grilla de
cuadraditos (*gcells*) y decide **por qué gcells y en qué capa** pasa cada
net. Su objetivo es que en ninguna gcell se pidan más pistas de las que hay.

Una **pista** (*track*) es un carril donde entra un cable de esa capa.

La primera línea, `Global adjustment: 30%`, es el margen que se reserva: el
routing global solo usa el 70 % de las pistas, para dejarle lugar al
routing detallado (que tiene que esquivar cosas y meter vías).

#### Tabla de recursos

Una fila por capa de metal (`li1`, `met1`, ..., `met5`, de abajo hacia
arriba).

| Columna | Qué es |
| :------ | :----- |
| `Layer` | La capa. `li1` es la capa local de las celdas: no se usa para rutear entre celdas, por eso tiene 0 pistas. |
| `Direction` | La dirección preferida de la capa. Se alternan (horizontal, vertical, horizontal, ...) para que los cables de capas vecinas se crucen sin chocar. |
| `Original` | Todas las pistas de esa capa, sumadas sobre todas las gcells. Las capas de arriba tienen menos porque sus cables son más anchos y más separados. |
| `Derated` | Las pistas que el routing global se permite usar, después de descontar el margen y las obstrucciones. |
| `Reduction` | Cuánto se descontó: el 30 % del margen más las **obstrucciones** (las SRAM, que bloquean met1-met4; los straps de alimentación de la PDN; los rieles de las celdas). Por eso met4 y met5, donde está la PDN, pierden más que el 30 %. |

#### Tabla de congestión final

| Columna | Qué es |
| :------ | :----- |
| `Layer` | La capa; la última fila, `Total`, suma todas. |
| `Resource` | Las pistas disponibles: las *derated* de la tabla anterior. |
| `Demand` | Las pistas que ocupan los cables que asignó el router. |
| `Usage` | `Demand / Resource`, en %. Es un **promedio** de todo el chip: puede haber zonas mucho más cargadas. |
| `Overflow` | Cuántas veces una gcell necesitó más pistas de las que tenía en esa capa. Tiene que ser **0**: si no, el routing global falla (`GRT-0116`) y el flujo se corta. |

#### Tabla de resumen

| Fila | Qué es |
| :--- | :----- |
| `HPWL after CTS (µm)` | La estimación de largo (semiperímetros) con el placement después de CTS: un poco mayor que la del TP2 porque CTS agregó buffers y nets. |
| `Global routing wirelength (µm)` | El largo según el routing global. Es mayor que el HPWL: un net con muchos pines necesita un árbol más largo que su semiperímetro, y el routing global mide con la resolución gruesa de las gcells. |
| `Routed nets` | Cuántos nets se rutearon. |
| `Clock nets` | Cuántos de esos nets son de clock (los del árbol). Se rutean con una regla especial, con más separación. |

### 3.2 `Antennas after global routing`

El **efecto antena** está explicado en la sección 4 del `README.md`.

#### Tabla de violaciones

| Fila | Qué es |
| :--- | :----- |
| `Nets with antenna violations (check after global routing)` | Nets que, con los recorridos del routing global, violan la regla de antena (paso 06). |
| `Pins with antenna violations` | Los pines afectados. Un net puede tener varios: cada compuerta que toca se chequea por separado. |

#### Tabla de reparación (`Repair, in steps`)

La reparación (paso 08) va por pasos. En cada uno vuelve a chequear y
arregla lo que puede, alternando dos técnicas. Cada fila es un paso.

| Columna | Qué es |
| :------ | :----- |
| `Step` | El número de paso. |
| `Violations found` | Violaciones que encontró al empezar ese paso. Tiene que ir bajando. |
| `Jumpers inserted` | Cuántos *jumpers* puso: partes del cable que se suben de capa, para cortar el tramo largo de metal conectado a la compuerta. `-` si ese paso usó diodos. |
| `Diodes inserted` | Cuántos diodos de antena puso al lado de las compuertas, para descargarlas. `-` si ese paso usó jumpers. |

### 3.3 `Detailed routing`

El routing detallado dibuja cada cable exacto. Primero rutea todo
permitiendo errores, y después repite **iteraciones** que arreglan las
violaciones de DRC hasta que no quede ninguna. Cuando termina, LibreLane
vuelve a chequear las antenas: si quedan, agrega diodos y rutea **todo de
nuevo** (una "Route" nueva).

#### Tabla de rutas e iteraciones

Cada fila es una ruta completa (`Route 0` es la primera; las siguientes son
después de agregar diodos).

| Columna | Qué es |
| :------ | :----- |
| `Route` | El número de ruta. |
| `Diodes added before` | Cuántos diodos se agregaron justo antes de esta ruta (0 en la primera). |
| `Iter 0`, `Iter 1`, ... | Cuántas violaciones de DRC quedaban **después** de esa iteración. Cuando llega a 0 la ruta termina, por eso las rutas que terminan antes tienen celdas vacías. |

#### Tabla de violaciones por tipo y capa

Las violaciones que quedaban después de la primera iteración de la primera
ruta (la columna `Iter 0` de `Route 0`), desglosadas.

Columnas: las capas. `li1`, `met1`, ..., `met5` son los metales; `mcon` es
el contacto de `li1` a `met1`, y `via` es la vía de `met1` a `met2` (`via2`,
... las de más arriba).

| Fila | Qué es |
| :--- | :----- |
| `Short` | Dos cables de nets distintos que se tocan: un cortocircuito. |
| `Metal Spacing` | Dos formas de metal más cerca que la distancia mínima permitida. |
| `Cut Spacing` | Dos vías (*cuts*) más cerca que lo permitido. |
| `Min Hole` | Un hueco dentro de una forma de metal más chico que el mínimo. |
| `Recheck` | Zonas que el router marcó para volver a revisar en la iteración siguiente. |

Puede haber otras filas según el diseño (por ejemplo `Min Area`: una forma
de metal demasiado chica).

#### Tabla de largo y vías por capa

El resultado final del routing detallado.

| Columna | Qué es |
| :------ | :----- |
| `Layer` | La capa. |
| `Wirelength (µm)` | El largo de cable en esa capa. La fila `Total` es el largo final que aparece en `qor.md`. |
| `Up-vias` | Cuántas vías van de esta capa a la de **arriba**. La fila `li1` son los contactos `li1` → `met1`, la fila `met1` las vías `met1` → `met2`, etc. `met5` no tiene capa arriba (`-`). `Total`: todas las vías. |

### 3.4 `Checks after detailed routing`

| Fila | Qué es |
| :--- | :----- |
| `DRC violations (detailed router)` | Violaciones de DRC que quedaron. Tiene que ser 0. |
| `Nets with antenna violations` | Nets con violaciones de antena al final, después de todas las reparaciones (paso 12). |
| `Antenna diodes (total)` | Todos los diodos de antena del layout: los de la reparación del paso 08 más los que agregó el routing detallado. |
| `Disconnected pins` | Pines de celdas que no están conectados a nada. |
| `Critical disconnected pins` | Los que sí deberían estar conectados (una entrada que maneja lógica). Tiene que ser 0. Los demás son normales: salidas que nadie usa, o el puerto 1 de las SRAM. |
| `Longest net (µm)` | El largo del net más largo del diseño. |
| `Filler instances inserted` | Celdas de relleno (`fill`, `decap`) que se pusieron en los huecos de las filas (paso 18). |

#### `Antenna violations left`

Una fila por cada pin que todavía viola la regla de antena.

| Columna | Qué es |
| :------ | :----- |
| `P / R` | `Partial / Required`: cuántas veces se pasa del límite. 3.42 quiere decir 3.42 veces lo permitido. |
| `Partial` | El *ratio* de antena encontrado: área de metal conectada a la compuerta (en esa capa) dividida por el área de la compuerta. |
| `Required` | El máximo *ratio* que permite la regla del PDK. |
| `Net` | El net con la violación. |
| `Pin` | El pin de compuerta afectado (`<instancia>/<pin>`). |
| `Layer` | La capa donde se viola. |

#### `Longest nets`

Los 5 nets más largos del layout final.

| Columna | Qué es |
| :------ | :----- |
| `Net` | El nombre del net. |
| `Length` | Su largo, en **mm**. |

---

## 4. `timing.md`: el timing

### 4.1 `Timing at each stage`

Una fila por cada análisis de timing (STA) a lo largo de los tres TP, todos
en la esquina típica `tt`. Sirve para ver cómo cambia el timing en cada
etapa.

| Fila | De dónde sale |
| :--- | :------------ |
| `TP1: synthesis (no wires)` | El STA del TP1, después de la síntesis: sin cables y con clock ideal. |
| `TP2: placement` | El STA del final del TP2: cables estimados con el placement, clock ideal. |
| `after CTS` | Paso 02 de esta corrida: el primer STA con el árbol de clock (clock propagado). |
| `after timing repair post-CTS` | Paso 04: después de la reparación del paso 03. Si no hubo nada que reparar, da igual que la fila anterior. |
| `after global routing` | Paso 09: los cables se estiman con los recorridos del routing global. Solo en corridas `rt_`. |
| `after detailed routing + RCX` | Paso 21: el STA final, con la resistencia y la capacidad de cada cable **extraídas** del layout (RCX). Solo en corridas `rt_`. |

| Columna | Qué es |
| :------ | :----- |
| `Stage` | La etapa. |
| `Setup WS (ns)` | *Worst slack* de setup: el slack del peor camino. Positivo = cumple; negativo = el dato llega tarde. |
| `Hold WS (ns)` | *Worst slack* de hold: positivo = cumple; negativo = el dato cambia demasiado rápido y pisa el valor anterior. |
| `Setup vio` | Cuántos caminos tienen slack de setup negativo (contados por su punto final). |
| `Hold vio` | Cuántos caminos tienen slack de hold negativo (contados por su punto final). |
| `Max slew vio` | Cuántos pines tienen un *slew* (tiempo de subida o bajada de la señal) mayor que el máximo permitido. |
| `Max cap vio` | Cuántos pines manejan más capacidad que el máximo que permite la celda. |
| `Clock latency min (ns)` | La latencia de clock más chica (flanco de subida), como en la sección 2.4. `0 (ideal)` en TP1 y TP2, que no tenían árbol. |
| `Clock latency max (ns)` | La latencia más grande. |
| `Clock skew (ns)` | `max − min`. |

### 4.2 `Corners, after detailed routing` (solo `make route`)

El STA final en las tres esquinas de proceso. Una **esquina** (*corner*) es
una combinación de proceso, tensión y temperatura:

| Fila | Qué es |
| :--- | :----- |
| `nom_ss_100C_1v60` | *Slow-slow*: transistores lentos, 1.60 V, 100 °C. Las celdas son más lentas. |
| `nom_tt_025C_1v80` | *Typical*: transistores típicos, 1.80 V, 25 °C. La esquina que se usa en el resto de los reportes. |
| `nom_ff_n40C_1v95` | *Fast-fast*: transistores rápidos, 1.95 V, −40 °C. Las celdas son más rápidas. |

El `nom_` del principio quiere decir que los cables se toman con su
resistencia y capacidad nominales.

Las columnas son las mismas que en la tabla 4.1 (sin las de clock).

### 4.3 `Critical setup path` y `Critical hold path`

El peor camino de setup y el peor de hold, en `tt`, en el último STA de la
corrida (el título dice de qué paso salen). Es la salida de
`report_checks` de OpenSTA.

**Encabezado:**

- `Startpoint`: donde empieza el camino (el flip-flop o la SRAM que lanza el
  dato, o un pin de entrada), y con qué flanco de qué clock.
- `Endpoint`: donde termina (el flip-flop que captura, o un pin de salida).
- `Path Group`: el grupo de caminos (el clock).
- `Path Type`: `max` para setup (el camino más **lento**), `min` para hold
  (el más **rápido**).

**Columnas** (cada línea es un pin del camino):

| Columna | Qué es |
| :------ | :----- |
| `Fanout` | Cuántos pines maneja el net que sale de ese pin. |
| `Cap` | La capacidad que maneja ese pin de salida (pF): cables más entradas. |
| `Slew` | El tiempo de subida o bajada de la señal en ese pin (ns). |
| `Delay` | Cuánto se sumó en esa línea (ns): el retardo de la celda (en las líneas de salida, `/X`, `/Y`, `/Q`) o del cable (en las líneas de entrada, `/A`, `/B`, ...). |
| `Time` | El tiempo acumulado desde el flanco de clock (ns). |
| `Description` | El pin, con `^` si la señal sube y `v` si baja, y el tipo de celda entre paréntesis. Las líneas que terminan en `(net)` nombran el cable que sale de ese pin. |

**Las dos mitades del reporte:**

1. **Llegada del dato** (*data arrival time*): desde el flanco de clock en
   `clk_i`, pasando por el árbol de clock hasta el pin de clock de quien
   lanza, y después por la lógica hasta el `Endpoint`. La última línea de
   esta parte es el `data arrival time`.
2. **Tiempo requerido** (*data required time*): cuándo tiene que llegar el
   dato como muy tarde (setup) o como muy temprano (hold):
   - `clock clk (rise edge)`: el flanco que captura (en setup, el siguiente:
     100 ns).
   - `clock network delay (propagated)`: la latencia del clock hasta quien
     captura. Si el `Endpoint` es un pin de salida es 0, porque el que
     captura está afuera del chip.
   - `clock uncertainty`: un margen de seguridad fijo del SDC (0.25 ns en
     setup, 0.1 ns en hold).
   - `clock reconvergence pessimism`: una corrección por la parte del árbol
     que comparten el camino de lanzamiento y el de captura.
   - `output external delay`: en un camino a un pin de salida, lo que tarda
     la señal **afuera** del chip (`set_output_delay` del SDC: 20 ns).
   - `library hold time` / `library setup time`: el tiempo que el flip-flop
     que captura necesita el dato estable después (hold) o antes (setup) del
     flanco.

**Slack:** setup: `required − arrival`; hold: `arrival − required`. Si es
positivo dice `(MET)` (cumple); si es negativo, `(VIOLATED)`.

En el camino crítico de setup del Ibex el `Startpoint` es una SRAM marcada
como `falling edge-triggered`: la SRAM lanza el dato con el flanco de
**bajada**, por eso el camino arranca en 50 ns (la mitad del período).
