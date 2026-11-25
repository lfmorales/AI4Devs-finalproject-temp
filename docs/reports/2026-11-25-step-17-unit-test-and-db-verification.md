# Paso 17: tests unitarios y verificación de la base de datos

**Fecha:** 2026-11-25
**Change:** `equativ-deals` (tareas 17.1 a 17.4)
**Commit probado:** `ce6be01 docs(reports): paso 16, revisión de los tests del change`
**Rama:** `feature/equativ-deals`

## Entorno

- **Backend:** Python 3.12.16, contra un `postgres:16` desechable de nombre propio (PostgreSQL 16.15), parado y borrado al terminar. Los tests derivan de él su base de pruebas y ejecutan `alembic upgrade head`.
- **Frontend y scripts:** Node 25.9.0 (el proyecto pide `>=22`).
- **Base de desarrollo:** la del stack Compose de este worktree. Ningún test la usa; se vigila para comprobarlo.

## 17.1 y 17.3: base de desarrollo antes y después

Conteo y suma de comprobación (`md5` del texto de las filas ordenadas por `id`) de las siete tablas de la tarea. El estado de partida es el que dejó la última ejecución E2E sobre datos recién sembrados (grupo 15).

| Tabla | Filas antes | Filas después | Suma antes | Suma después |
|---|---:|---:|---|---|
| `campaign_lines` | 13 | 13 | `13b77f01…dd` | `13b77f01…dd` |
| `daily_deliveries` | 126 | 126 | `de5c2b68…81` | `de5c2b68…81` |
| `dsp_catalog_lines` | 5 | 5 | `5c3db62a…e2` | `5c3db62a…e2` |
| `dsp_mappings` | 3 | 3 | `209bd232…f2` | `209bd232…f2` |
| `ingestion_batches` | 3 | 3 | `dd19c33d…91` | `dd19c33d…91` |
| `ingestion_exceptions` | 5 | 5 | `ffbbe60b…96` | `ffbbe60b…96` |
| `applied_rates` | 5 | 5 | `b8c3d2c5…16` | `b8c3d2c5…16` |
| `alembic_version` | 1 (`950895fa2d75`) | 1 (`950895fa2d75`) | | |

La salida de las dos capturas es idéntica byte a byte. **Los tests no cambiaron nada y no hizo falta restaurar la base.**

## 17.2: ejecuciones

### Tests de las tareas 1 a 15, primero

Los 46 ficheros de test nuevos o modificados desde el spec (`git diff --diff-filter=AM e28272e HEAD -- backend/tests`):

```
pytest <los 46 ficheros> -q
850 passed in 61.42s (0:01:01)
```

### Cinco suites, dos ejecuciones de cada una

| Suite | Comando | Ejecución 1 | Ejecución 2 |
|---|---|---|---|
| Backend completo | `pytest -q` (en `backend/`) | 2697 passed, 1 deselected, 0 skipped, 160,98 s | 2697 passed, 1 deselected, 0 skipped, 155,04 s |
| Aceptación de margen (38) | `pytest tests/acceptance tests/api/test_acceptance_closed_month_database.py tests/api/test_acceptance_running_month_database.py -q` | 38 passed, 7,75 s | 38 passed, 8,03 s |
| Vitest con typecheck | `npx vitest run` y `npx tsc --noEmit` (en `frontend/`) | 65 ficheros, 654 passed, 86,08 s; tsc: 0 errores | 65 ficheros, 654 passed, 61,71 s; tsc: 0 errores |
| `node --test` de `e2e/` | los cuatro ficheros de `e2e/support/` y `e2e/scripts/` | 48 passed, 0 fail, 0 skipped | 48 passed, 0 fail, 0 skipped |
| `node --test` de la raíz | `node --test scripts/*.test.mjs` | 15 passed, 0 fail, 0 skipped | 15 passed, 0 fail, 0 skipped |

Notas:

- El «1 deselected» es el test marcado `slow`, que `pyproject.toml` excluye por defecto.
- Las 38 pruebas de aceptación corren y pasan, tanto aparte como dentro de la suite completa.
- `git ls-files '*.test.mjs' '*.test.js'` lista seis ficheros fuera de `frontend/` (que usa Vitest): los cuatro de `e2e/` y los dos de `scripts/`.
- Sin fallos intermitentes: las dos ejecuciones de cada suite dan lo mismo.
- No se ejecutó el E2E de Playwright aquí: es el paso 19.

### mypy

Con el comando de `docs/base-standards.md` §4, sobre los 96 ficheros Python del backend que el change toca (82 modificados y 14 nuevos), comparado con el commit del spec en un worktree temporal y contando solo los errores situados en esos ficheros (el resto son de módulos que mypy alcanza al seguir importaciones):

| | En `e28272e` | Ahora |
|---|---:|---:|
| Errores en los 82 ficheros modificados | 633 | 628 |
| Errores que aparecen ahora y no en el spec | | **0** |
| Errores del spec que ya no aparecen | | 5 |
| Errores en los 14 ficheros nuevos | | 1 |

El único error de los ficheros nuevos es `import-not-found` de `fastapi.testclient` en `tests/api/test_margin_target_flights.py`: mypy se ejecuta sin `fastapi` instalado y todos los tests de API dan ese mismo error.

## Reconciliación con el cierre del change anterior

Referencia: el commit del spec, `e28272e`, medido de nuevo en un worktree temporal con los mismos comandos, no tomado de memoria. Sus cifras coinciden con las del cierre del change `ctv-and-delivery-metric` (2418 recogidas en backend, 622 en Vitest, 42 de Playwright, 46 y 15 de `node --test`).

| Suite | En `e28272e` | Ahora | Diferencia | Origen |
|---|---:|---:|---:|---|
| Backend, recogidas | 2418 | 2697 | +279 | tabla siguiente |
| Vitest | 622 | 654 | +32 | grupo 1: +13 (selector de compromiso del formulario, tarea 1.7); grupo 14: +19 (4 del estado, 2 del cierre, 6 del margen y 7 del mapeo de Equativ) |
| E2E (`playwright test --list`) | 42 | 45 | +3 | grupo 15: uno en `campaign.spec.ts`, uno en `status.spec.ts` y uno en `margin.spec.ts` |
| `node --test` de `e2e/` | 46 | 48 | +2 | grupo 1: `campaigns.test.mjs` (de 4 a 6) |
| `node --test` de la raíz | 15 | 15 | 0 | el change no los toca |

Vitest se midió además en `4e5caf3` (635) y en `0328719` (635) para atribuir la diferencia a los dos grupos.

Nota para repetir la medida de `node --test` de `e2e/` en un worktree temporal: hace falta enlazar `e2e/node_modules`; sin él, `campaigns.test.mjs` no carga y cuenta como un único test fallido (43 en lugar de 46 o 48).

### Backend: recogidas en cada commit del change

Medidas con `pytest --collect-only -q` en cada commit (el `deselected` aparte):

| Commit | Recogidas | Δ | Grupo |
|---|---:|---:|---|
| `e28272e` spec | 2418 | | |
| `4e5caf3` compromiso o objetivo de volumen en cada línea | 2457 | +39 | 1 |
| `c8c74d4` gasto, ingreso comunicado y costes de datos en las entregas | 2480 | +23 | 2 |
| `8c8bf7f` cliente de la API de informes de Equativ | 2539 | +59 | 3 |
| `c8fc9f4` ingesta de Equativ con `--dsp` y origen del lote | 2564 | +25 | 4 |
| `a3db1dd` mapeo de Equativ escrito por operaciones | 2588 | +24 | 5 |
| `a0b2177` línea sin entrega en Equativ | 2594 | +6 | 6 |
| `5d0486b` margen de las líneas con objetivo | 2621 | +27 | 7 |
| `51b3451` extraprima sobre el bruto servido | 2625 | +4 | 8 |
| `e4f65fe` bruto, compromiso y avisos en los totales | 2636 | +11 | 9 |
| `6a69d83` un total con un hijo de métrica mezclada es nulo | 2638 | +2 | 9 (9.3 y 9.4) |
| `40d663c` el repositorio lee el compromiso y los importes | 2641 | +3 | 10 |
| `4350650` el cierre congela el ingreso y el bruto | 2667 | +26 | 11 |
| `bd82666` riesgo del mes cerrado | 2667 | 0 | |
| `87087dc` sin aviso de sobreentrega en las líneas con objetivo | 2682 | +15 | 12 |
| `0328719` compromiso, bruto y avisos en las respuestas | 2688 | +6 | 13 |
| `c377dd7` pantallas | 2688 | 0 | 14 (frontend) |
| `3585568` etiqueta de venta en campañas mixtas | 2688 | 0 | |
| `05aa41f` demo de Deal y sus E2E | 2697 | +9 | 15 |
| `ce6be01` informe del paso 16 | 2697 | 0 | |

Suma de las diferencias: 2697 − 2418 = **279**.

## 17.4: estado de la tarea

Los tests del change y las cinco suites pasan dos veces, mypy no añade ningún error en los ficheros del change, la base de desarrollo no cambió y este informe existe: el paso 17 queda completo.
