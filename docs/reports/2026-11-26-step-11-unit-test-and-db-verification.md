# Paso 11: tests unitarios y verificación de la base de datos

**Fecha:** 2026-11-26
**Change:** `closing-snapshot` (tareas 11.1 a 11.4)
**Commit probado:** `c9535d7 docs(reports): paso 10, revisión de los tests que cambian con el snapshot`, más la corrección de tipos de este paso (ver «mypy»)
**Rama:** `feature/closing-snapshot`

## Entorno

- **Backend:** Python 3.12.16, contra un `postgres:16` desechable de nombre propio (PostgreSQL 16.15), parado al terminar cada grupo. Los tests derivan de él su base de pruebas y ejecutan `alembic upgrade head`.
- **Frontend y scripts:** Node 24.17.0 (el proyecto pide `>=22`).
- **Base de desarrollo:** la del stack Compose de este worktree, en la revisión `3a08cce1c979`. Ningún test la usa; se vigila para comprobarlo.

## 11.1 y 11.3: base de desarrollo antes y después

Conteo y suma de comprobación (`md5` del texto de las filas ordenadas por `id`; `month_closing_batches`, que no tiene `id`, por su clave) de las seis tablas de la tarea. El estado de partida es el que dejó la última ejecución de Playwright sobre datos recién sembrados (grupo 8), con los dos cierres que hacen los E2E.

| Tabla | Filas antes | Filas después | Suma antes | Suma después |
|---|---:|---:|---|---|
| `applied_rates` | 5 | 5 | `085aa557…9d` | `085aa557…9d` |
| `month_closings` | 2 | 2 | `37cfcd9f…56` | `37cfcd9f…56` |
| `month_closing_batches` | 2 | 2 | `8d37ab87…4b` | `8d37ab87…4b` |
| `closed_flight_snapshots` | 5 | 5 | `4dca7f52…3c` | `4dca7f52…3c` |
| `daily_deliveries` | 127 | 127 | `a967938b…e6` | `a967938b…e6` |
| `ingestion_batches` | 3 | 3 | `6973bcfe…6f` | `6973bcfe…6f` |
| `alembic_version` | 1 (`3a08cce1c979`) | 1 (`3a08cce1c979`) | | |

La salida de las dos capturas es idéntica byte a byte. **Los tests no cambiaron nada y no hizo falta restaurar la base.**

## 11.2: ejecuciones

### Tests de las tareas 1 a 9, primero

Los 20 ficheros de test del backend nuevos o modificados desde el spec (`git diff --diff-filter=AM f352be5 HEAD -- backend/tests`, 4 de ellos nuevos):

```
pytest <los 20 ficheros> -q
755 passed in 61.84s (0:01:01)
```

### Cinco suites, dos ejecuciones de cada una

| Suite | Comando | Ejecución 1 | Ejecución 2 |
|---|---|---|---|
| Backend completo | `pytest -q` (en `backend/`) | 2830 passed, 1 deselected, 0 skipped, 187,39 s | 2830 passed, 1 deselected, 0 skipped, 226,09 s |
| Aceptación de margen (39) | `pytest tests/acceptance tests/api/test_acceptance_closed_month_database.py tests/api/test_acceptance_running_month_database.py -q` | 39 passed, 9,89 s | 39 passed, 6,96 s |
| Vitest con typecheck | `npx vitest run` y `npm run typecheck` (en `frontend/`) | 66 ficheros, 665 passed, 42,17 s; tsc: 0 errores | 66 ficheros, 665 passed, 47,19 s; tsc: 0 errores |
| `node --test` de `e2e/` | los cuatro ficheros de `e2e/support/` y `e2e/scripts/` | 48 passed, 0 fail, 0 skipped | 48 passed, 0 fail, 0 skipped |
| `node --test` de la raíz | `node --test scripts/*.test.mjs` | 15 passed, 0 fail, 0 skipped | 15 passed, 0 fail, 0 skipped |

Después de la corrección de tipos de este paso, el backend completo se ejecutó una tercera vez: 2830 passed, 1 deselected, 242,97 s. Los tres ficheros de `run_ingestion` que toca la corrección pasan (66 passed).

Notas:

- El «1 deselected» es el test marcado `slow`, que `pyproject.toml` excluye por defecto.
- Las 39 pruebas de aceptación corren y pasan, tanto aparte como dentro de la suite completa: la hoja privada que las alimenta está presente.
- `git ls-files '*.test.mjs' '*.test.js'` lista seis ficheros fuera de `frontend/` (que usa Vitest): los cuatro de `e2e/` y los dos de `scripts/`.
- Sin fallos intermitentes: las dos ejecuciones de cada suite dan lo mismo.
- No se ejecutó el E2E de Playwright aquí: es el paso 13. Su última ejecución, en el grupo 8 sobre datos limpios, dio 45 passed.

### mypy

Con el comando de `docs/base-standards.md` §4, sobre los 40 ficheros Python del backend que el change toca (32 modificados y 8 nuevos), comparado con el commit del spec en un worktree temporal. Se cuentan solo los errores situados en esos ficheros (el resto son de módulos que mypy alcanza al seguir importaciones) y se comparan por fichero y mensaje, sin el número de línea, que se desplaza con cada cambio:

| | En `f352be5` | Ahora |
|---|---:|---:|
| Errores en los 32 ficheros modificados | 253 | 237 |
| Errores que aparecen ahora y no en el spec | | **0** |
| Errores del spec que ya no aparecen | | 16 |
| Errores en los 8 ficheros nuevos | | 1 |

**Corrección de este paso.** La primera comparación encontró un error nuevo en `tests/scripts/test_run_ingestion.py:114`: `Scenario.count()` devolvía `int | None` donde declara `int`. Venía del grupo 7: al tipar `Scenario.__init__`, `self.session` pasó a ser `Session` y su `scalar()` dejó de ser `Any`. Aquella comparación contó errores por fichero y el total bajó (de 24 a 19), lo que escondió este error nuevo entre los que desaparecieron; esta compara cada error. Se corrige con el patrón del código de la aplicación, `int(... or 0)`.

El único error de los ficheros nuevos es `import-not-found` de `fastapi.testclient` en `tests/api/test_margin_delivery_change_endpoint.py`: mypy se ejecuta sin `fastapi` instalado y todos los tests de API dan ese mismo error.

## Reconciliación con el cierre de equativ-deals

Referencia: las cifras del cierre de `equativ-deals` (2697 en backend, 38 de aceptación, 654 en Vitest, 48 y 15 en `node --test`, 45 en Playwright). Se midieron de nuevo en el commit del spec de este change, `f352be5`, en un worktree temporal y con los mismos comandos: coinciden todas, salvo `node --test` de la raíz (ver la nota bajo la tabla).

| Suite | En `f352be5` | Ahora | Diferencia | Origen |
|---|---:|---:|---:|---|
| Backend, recogidas | 2697 | 2830 | +133 | tabla siguiente |
| Aceptación | 38 | 39 | +1 | grupo 6: la prueba en base de datos de un mes cerrado que se reingiere con otras cifras (`test_acceptance_closed_month_database.py`) |
| Vitest | 654 | 665 | +11 | grupo 8 (`b5b7d40`): 7 de `delivery-change.test.tsx` (etiqueta y ayuda, margen informativo y diferencias, cifras cerradas, diferencias solo en target, OTS, sin etiqueta en vuelos sin cambio, recuentos en los tres niveles), 2 de `closingsMessage` en `messages.test.ts` y 2 del aviso de varios cierres en `margin-closing.test.tsx`. Los ajustes de texto del grupo 8 y la corrección del grupo 10 cambian tests, no añaden |
| `node --test` de `e2e/` | 48 | 48 | 0 | el change no toca ningún `*.test.mjs` |
| `node --test` de la raíz | 15 | 15 | 0 | ídem |
| E2E (`playwright test --list`) | 45 | 45 | 0 | `09b5dff` solo cambia una comprobación de `margin.spec.ts` (el texto del diálogo de cierre); la especificación prueba el aviso en la API y en Vitest, no en E2E |

Nota sobre `node --test` de la raíz en un worktree temporal: da 14 de 15, tanto en `f352be5` como en `c9535d7`. Falla `development mounts only the public directory, read-only, and selects the test issuer`, que lee la configuración de Compose de la carpeta donde se ejecuta; en el worktree real pasan los 15. Para repetir allí la medida de Vitest y de `--list` hay que enlazar `frontend/node_modules` y `e2e/node_modules`.

### Backend: recogidas en cada commit del change

Medidas con `pytest --collect-only -q` en cada commit (el `deselected` aparte):

| Commit | Recogidas | Δ | Grupo | Origen |
|---|---:|---:|---|---|
| `f352be5` spec | 2697 | | | |
| `7d739d7` tablas de cabecera y snapshot | 2723 | +26 | 0 y 1 | `test_closing_snapshot_migration.py` |
| `33e00db` snapshot de un vuelo cerrado | 2765 | +42 | 2 | 32 de `test_closed_flight.py`; 10 de las pruebas que recorren módulos: 4 de integridad del margen, 2 de pureza del dominio y 4 del guardián de la tarifa de plataforma |
| `08836bd` aviso y días en meses cerrados | 2796 | +31 | 3 | 18 de la comprobación, 3 de totales, 6 de `test_closed_months.py`, 3 del guardián (1 test y 2 por el módulo nuevo) y 1 de pureza |
| `cc36a15` el cierre escribe cabecera y snapshots | 2803 | +7 | 4 | 4 de repositorio y 3 de servicio |
| `34b5e97` lectura del snapshot | 2811 | +8 | 5 | 3 de repositorio y 5 de servicio; el test de la reexpresión se invierte, no se añade |
| `65bfe76` `closings` y aviso en las respuestas | 2826 | +15 | 6 | 8 de `test_margin_delivery_change_endpoint.py`, 1 de `closings` igual a 2, 5 de descripciones del esquema y la prueba de aceptación nueva |
| `45ded4d` días en meses cerrados en la ingesta | 2832 | +6 | 7 | 4 de la salida y 2 del rango personalizado |
| `b5b7d40` aviso en pantalla | 2832 | 0 | 8 | frontend |
| `09b5dff` texto del diálogo en E2E | 2832 | 0 | 8 | E2E |
| `2e6dafb` sin bruto congelado de entrada | 2830 | −2 | 9 | 5 tests del bruto dado sustituidos por 3 |
| `c9535d7` informe del paso 10 | 2830 | 0 | 10 | cambia tests, no añade |

Suma de las diferencias: 2830 − 2697 = **133**.

## 11.4: estado de la tarea

Los tests del change y las cinco suites pasan dos veces, mypy no añade ningún error en los ficheros del change, la base de desarrollo no cambió y este informe existe: el paso 11 queda completo.
