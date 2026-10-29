# Árbol de clock y routing con LibreLane (sky130)

Este proyecto es la **tercera parte** del trabajo práctico. Toma el CPU
[Ibex] ya ubicado (*placed*) en la segunda parte (repositorio `up-tp2`) y
termina la implementación física con [LibreLane] y OpenROAD:

1. **CTS** (*clock tree synthesis*): construye el árbol de buffers que lleva
   el clock a todos los flip-flops y a las SRAM, y repara el timing con el
   clock real.
2. **Routing:** dibuja los cables de todas las señales, primero de forma
   aproximada (**routing global**) y después exacta, pista por pista
   (**routing detallado**). Incluye la reparación de antenas y el relleno
   (*fill*) de los huecos de las filas.
3. **Extracción y STA final:** calcula la resistencia y la capacidad de los
   cables ruteados (RCX) y hace el análisis de timing en tres esquinas.

**Acá no se sintetiza ni se ubica nada de nuevo:** el layout se importa del
TP2. El signoff (DRC y LVS del layout final) no es parte de este TP.

[LibreLane]: https://github.com/librelane/librelane
[Ibex]: https://github.com/lowRISC/ibex

---

## 1. Instalación

Se usan **el mismo contenedor y el mismo PDK** que en el TP1 y el TP2, así que
no hay que instalar ni descargar nada nuevo. La GUI se usa igual que en el TP2
(sección 1.2 de su `README.md`; en Windows y macOS, ver
[docs/gui_windows_mac.md](docs/gui_windows_mac.md)).

Clonar este repositorio **al lado** de los anteriores:

```bash
cd <directorio donde están up-tp1 y up-tp2>
git clone https://github.com/miguel9554/up-tp3.git
cd up-tp3
```

```
.
├── up-tp1/     el proyecto del TP1
├── up-tp2/     el proyecto del TP2, con sus corridas en designs/ibex/runs/
└── up-tp3/     este proyecto
```

Si lo ubicás en otro lado no pasa nada: al importar (sección 2) se indica la
ruta a la corrida del TP2.

---

## 2. Importar el placement del TP2

Elegí la corrida de placement del TP2 (una `pl_...` hecha con `make place`,
por ejemplo la `pl_ref_...` del ejercicio 2) e indicá **su directorio**:

```bash
ls ../up-tp2/designs/ibex/runs/
make import-tp2 TP2_RUN=../up-tp2/designs/ibex/runs/pl_ref_2026-10-22_15-52-28
```

Esto copia a `designs/ibex/tp2/`:

| Archivo            | Qué es                                                     |
| :----------------- | :--------------------------------------------------------- |
| `ibex_top.odb`     | el layout después del placement detallado: la entrada de CTS |
| `ibex_top.def`     | el mismo layout, en formato DEF (texto)                     |
| `ibex_top.nl.v`    | el netlist después del placement (con los buffers de reparación) |
| `ibex_top.pnl.v`   | el mismo netlist, con las conexiones de alimentación        |
| `ibex_top.h.json`  | encabezado JSON del diseño (lo usa LibreLane para las macros) |
| `state.json`       | estado inicial de LibreLane: el layout y las métricas del TP2 |
| `reports/`         | los reportes del TP2 (`qor.md`, `placement.md`, `timing.md`, ...), para comparar |
| `tp1_metrics.json` | las métricas del TP1, para comparar el timing desde la síntesis |
| `SOURCE`           | nombres de las corridas del TP2 y del TP1 de las que salió  |

La corrida tiene que haber terminado el placement (el STA del paso 20 del
TP2) y tener la **configuración original** (diseño `ibex_top`, biblioteca
`hd`, período de 100 ns); si no, el import falla y lo avisa.

El floorplan (die, pines, macros, PDN) viene incluido en el layout: no hace
falta el footprint ni `macro_placement.cfg`.

---

## 3. El flujo

### 3.1 Configuración

Todo está en `designs/ibex/`:

```
designs/ibex/
├── config.json           configuración de LibreLane
├── constraints.sdc       restricciones de timing (las del TP2, con el clock propagado)
├── tp2/                  lo importado del TP2 (sección 2)
└── runs/                 las corridas
```

`config.json` es el del TP2 sin lo que solo usaba el floorplan (el
footprint, la ubicación de las macros y el tamaño del die). Las variables de
CTS y routing toman el valor por defecto de LibreLane; la lista completa,
con su descripción, está en la documentación:
<https://librelane.readthedocs.io/en/latest/reference/step_config_vars.html>.
Algunas que aparecen en los reportes:

| Variable | Valor por defecto | Qué controla |
| :------- | :---------------- | :----------- |
| `CTS_CLK_BUFFERS` | `clkbuf_8`, `clkbuf_4`, `clkbuf_2` | las celdas que CTS puede usar como buffers del árbol |
| `CTS_ROOT_BUFFER` | `clkbuf_16` | el buffer de la raíz del árbol, el que maneja todo el resto |
| `RT_MIN_LAYER` / `RT_MAX_LAYER` | `met1` / `met5` | las capas de metal en que se puede rutear |
| `GRT_ADJUSTMENT` | `0.3` | fracción de las pistas que el routing global reserva (no usa), para dejar margen al detallado |
| `GRT_ANTENNA_REPAIR_ITERS` | `3` | iteraciones de reparación de antenas después del routing global |
| `DRT_OPT_ITERS` | `64` | máximo de iteraciones del routing detallado para eliminar violaciones de DRC |
| `DRT_ANTENNA_REPAIR_ITERS` | `3` | veces que, después del routing detallado, se agregan diodos y se vuelve a rutear si quedan antenas |
| `DRT_THREADS` | todos los núcleos | cuántos núcleos usa el routing detallado |
| `RUN_POST_GRT_DESIGN_REPAIR` | `false` | reparación de max slew / max cap después del routing global (desactivada) |
| `RUN_POST_GRT_RESIZER_TIMING` | `false` | reparación de setup / hold después del routing global (desactivada) |

### 3.2 El SDC

`constraints.sdc` es el del TP2 cambiando la última línea:

```tcl
set_propagated_clock [all_clocks]
```

En el TP1 y el TP2 el clock era **ideal**: llegaba a todos los flip-flops en
el mismo instante, sin retardo. Desde CTS hay un árbol de clock de verdad, y
con el clock **propagado** OpenSTA calcula cuándo llega realmente el flanco a
cada flip-flop, a través de los buffers y cables del árbol.

### 3.3 Correr

```bash
make cts NAME=ref       # solo CTS y su reparación de timing (~2-3 minutos)
make route NAME=ref     # CTS + routing + extracción + STA (~25 minutos con 14 núcleos; con 4, una hora o más)
```

`make route` **vuelve a hacer el CTS** (es determinístico: da lo mismo que
`make cts`) y después sigue con el routing. Cada corrida crea un directorio
nuevo en `designs/ibex/runs/`: `cts_<nombre>_<fecha>_<hora>` para `make cts`
y `rt_<nombre>_<fecha>_<hora>` para `make route`. `NAME` es opcional.

El routing detallado es el paso más largo y usa todos los núcleos de la
máquina. Si tu computadora tiene poca memoria o pocos núcleos puede tardar
bastante más: dejalo corriendo. Si se interrumpe, hay que volver a correr
`make route` desde el principio.

Los pasos de cada corrida (cada uno es un subdirectorio numerado):

| Paso | Directorio | Qué hace |
| ---: | :--------- | :------- |
| 1 | `01-openroad-cts` | CTS: construye el árbol de clock y vuelve a legalizar el placement (los buffers nuevos tienen que entrar en las filas) |
| 2 | `02-openroad-stamidpnr-1` | STA después de CTS, ya con el clock propagado |
| 3 | `03-openroad-resizertimingpostcts` | reparación de timing con el clock real: setup y hold (buffers y cambios de tamaño) |
| 4 | `04-openroad-stamidpnr-2` | STA después de la reparación |
| 5 | `05-openroad-globalrouting` | routing global: decide por qué gcells y capas pasa cada net |
| 6 | `06-openroad-checkantennas` | verifica las reglas de antena sobre el routing global |
| 7 | `07-odb-diodesonports` | diodos en los pines del bloque (desactivado: no hace nada) |
| 8 | `08-openroad-repairantennas` | repara las antenas: cambios de capa (*jumpers*) y diodos |
| 9 | `09-openroad-stamidpnr-3` | STA con los cables estimados a partir del routing global |
| 10 | `10-openroad-detailedrouting` | routing detallado: dibuja cada cable sobre las pistas, sin violaciones de DRC, y repara las antenas que queden |
| 11 | `11-odb-removeroutingobstructions` | quita obstrucciones auxiliares del routing (no cambia nada en este diseño) |
| 12 | `12-openroad-checkantennas-1` | verifica las antenas sobre los cables definitivos |
| 13 | `13-checker-trdrc` | falla si quedaron violaciones de DRC del router |
| 14 | `14-odb-reportdisconnectedpins` | busca pines de celdas que no quedaron conectados |
| 15 | `15-checker-disconnectedpins` | falla si alguno de esos pines es crítico |
| 16 | `16-odb-reportwirelength` | largo de cada net ruteado (`wire_lengths.csv`) |
| 17 | `17-checker-wirelength` | avisa si algún net es demasiado largo |
| 18 | `18-openroad-fillinsertion` | llena los huecos de las filas con celdas de relleno (*fill* y *decap*) |
| 19 | `19-odb-cellfrequencytables` | tablas de cuántas celdas hay de cada tipo |
| 20 | `20-openroad-rcx` | extracción de parásitos (RCX): resistencia y capacidad de cada cable, en archivos SPEF |
| 21 | `21-openroad-stapostpnr` | STA final, con los parásitos extraídos, en las tres esquinas |

`make cts` termina en el paso 4. Si un paso falla, el error está al final de
la salida y en `<corrida>/<paso>/*.log`.

---

## 4. Reportes

Cada corrida escribe en `<corrida>/reports/`:

| Archivo      | Contenido                                                          | Requiere |
| :----------- | :----------------------------------------------------------------- | :------- |
| `qor.md`     | Resumen: celdas, wirelength, DRC, antenas y el timing en cada etapa (TP1 → routing) |  |
| `cts.md`     | Árbol de clock: nets de clock, buffers, niveles, latencia, skew, reparación de timing y potencia | |
| `routing.md` | Routing global (uso de cada capa, overflow), routing detallado (iteraciones, violaciones, largo por capa, vías), antenas, celdas de relleno | `route` |
| `timing.md`  | Timing en cada etapa, timing en las tres esquinas y caminos críticos | |

Qué es cada fila y cada columna de cada tabla: [docs/reportes.md](docs/reportes.md).

Algunas definiciones:

- **Latencia de clock:** cuánto tarda el flanco de clock en llegar desde el
  pin `clk_i` hasta el pin de clock de un flip-flop (o de una SRAM). Con el
  clock ideal es cero.
- **Skew:** la diferencia entre la latencia más grande y la más chica. CTS
  trata de que sea chico: que el flanco llegue a todos casi a la vez.
- **Gcell:** el routing global divide el chip en una grilla de cuadrados
  (*gcells*) y decide por qué gcells pasa cada net, sin dibujar el cable
  exacto. Cada gcell tiene una cantidad de pistas disponibles por capa.
- **Overflow:** cuántas pistas faltan, en las gcells donde los nets que
  tienen que pasar son más que las pistas disponibles. Tiene que ser 0.
- **Violación de DRC del router:** dos cables demasiado cerca, un cable
  demasiado angosto, un cortocircuito, etc. El routing detallado itera hasta
  que no quede ninguna.
- **Antena:** durante la fabricación, un cable largo conectado solo a la
  compuerta de un transistor acumula carga y puede dañarla. Se repara
  agregando un **diodo** que descarga el cable, o cortando el cable con un
  salto a otra capa.
- **RCX** (extracción de parásitos): a partir de la forma real de cada cable
  (capa, largo, ancho, vecinos) calcula su resistencia y su capacidad. Las
  escribe en un archivo SPEF que usa el STA final.
- **Esquinas:** `ss` (transistores lentos, 1.60 V, 100 °C), `tt` (típicos,
  1.80 V, 25 °C) y `ff` (rápidos, 1.95 V, −40 °C). El STA final analiza las
  tres; los STA intermedios, solo `tt`.

**Nota:** el archivo `clock.rpt` de cada STA dice `Propagated: no` y
`Virtual: yes`. Es un error del script de LibreLane que escribe ese encabezado
(escribe una propiedad en lugar de la otra): el clock sí está propagado. Lo
confirma `unpropagated.rpt`, que lista los clocks **no** propagados y está
vacío. Las latencias de `clock.rpt` son las correctas.

---

## 5. La GUI de OpenROAD

Se usa igual que en el TP2:

```bash
make gui                         # última corrida, en su último estado
make gui RUN=rt_ref_...          # otra corrida
make gui RUN=rt_ref_... STEP=05  # la corrida tal como quedó después del paso 05
```

`STEP` es el número de dos dígitos del paso (tabla de la sección 3.3). Si ese
paso no modifica el layout, se abre el último layout anterior. Por ejemplo:
`STEP=01` (árbol de clock, todavía sin cables), `STEP=10` (todos los cables
ruteados) y `STEP=18` (con las celdas de relleno). Después del routing global
(`STEP=05`) todavía no hay cables dibujados: el routing global solo decide
por dónde va a pasar cada net.

Además de lo del TP2 (Display Control, Inspector, regla con `K`, Find,
Timing Report, `save_image`), en esta parte sirve:

| Qué | Cómo |
| :-- | :--- |
| Ver solo los cables de una capa | Display Control → `Layers`: desmarcá todas y marcá una (`met1`, ..., `met5`) |
| Ocultar las celdas para ver los cables | Display Control → `Instances`: desmarcalas |
| Ocultar la alimentación (PDN) | Display Control → `Nets` → `Power` y `Ground` |
| Ver solo la red de clock | Display Control → `Nets`: dejá marcado solo `Clock` |
| El árbol de clock | menú **Windows → Clock Tree Viewer** → `Update`: dibuja el árbol (cada buffer a su altura según su latencia); al hacer clic en un buffer se selecciona en el layout |
| Resaltar un net | botón **Find**, tipo `Net`, y el nombre (por ejemplo `clk`) |

La consola Tcl (abajo) acepta cualquier comando de OpenROAD, por ejemplo
`report_clock_skew` o `report_checks -path_delay min` (peor camino de hold).

Para cerrar la GUI, cerrá la ventana (o `exit` en la consola Tcl).

---

## 6. Referencia

### Targets de make

| Comando                          | Qué hace                                              |
| :------------------------------- | :---------------------------------------------------- |
| `make import-tp2 TP2_RUN=<dir>`  | Importa el layout de una corrida de placement del TP2  |
| `make cts`                       | CTS + reparación de timing + STA                      |
| `make route`                     | CTS + routing global y detallado + extracción + STA en tres esquinas |
| `make gui`                       | Abre una corrida en la GUI de OpenROAD (`RUN=`, `STEP=`) |
| `make report`                    | Regenera los reportes de la última corrida            |
| `make shell`                     | Abre una terminal dentro del contenedor               |
| `make clean`                     | Borra todas las corridas                              |

`NAME=<nombre>` agrega un nombre al directorio de la corrida en `cts` y
`route`.

### Problemas frecuentes

| Problema                                          | Solución |
| :------------------------------------------------ | :------- |
| `the TP2 placement was not imported yet`          | `make import-tp2 TP2_RUN=<corrida del TP2>` |
| `did not finish the placement`                    | Elegí una corrida `pl_...` completa, o en el TP2: `make place NAME=ref` |
| `expected 100` / `expected sky130_fd_sc_hd`       | La corrida del TP2 tiene la configuración cambiada: usá otra |
| El routing tarda mucho o la máquina se queda sin memoria | Cerrá otros programas. En Docker Desktop (Windows/macOS), dale más memoria en Settings → Resources |
| `DISPLAY is not set`                              | Corré `make gui` desde una terminal del escritorio, no por SSH |
| La GUI no abre en Windows o macOS                 | Ver [docs/gui_windows_mac.md](docs/gui_windows_mac.md) |
| Un paso falla                                     | Leé el final de `<corrida>/<paso>/*.log` |

### Más información

- Documentación de LibreLane: <https://librelane.readthedocs.io>
- Documentación de OpenROAD (CTS, routing global y detallado, GUI):
  <https://openroad.readthedocs.io>
- Documentación del PDK sky130: <https://skywater-pdk.readthedocs.io>
