# Paso 14: tests unitarios y verificación de la base de datos

**Fecha:** 2026-11-27
**Change:** `committed-billing-and-review` (tareas 14.1 a 14.4)
**Commit probado:** `1dbb441 test(review): record the tests whose meaning the billing rule changed`, más la corrección de tipos de este paso (ver «mypy»)
**Rama:** `feature/committed-billing-and-review`

## Entorno

- **Backend:** Python 3.12.16. Corre contra un `postgres:16` desechable de nombre propio (PostgreSQL 16.15), que se para al terminar el grupo. Los tests derivan de él su base de pruebas y ejecutan `alembic upgrade head`.
- **Frontend y scripts:** Node 24.17.0 (el proyecto pide `>=22`).
- **Base de desarrollo:** la del stack Compose de este worktree, en la revisión `f1c6d2b84a57` (la última del change). Ningún test la usa; se vigila para comprobarlo.

## 14.1 y 14.3: base de desarrollo antes y después

Recuento y suma de comprobación de las tablas de la tarea. La suma es el `md5` del texto de las filas ordenadas por `id`. Se añade `campaign_line_periods` entera, porque el arrastre vive en sus columnas.

El punto de partida es la base recién sembrada por `e2e/scripts/reset-data.sh`, que se ejecutó tras el último Playwright del grupo 12. Por eso no hay nada cerrado, revisado, ajustado ni arrastrado.

| Tabla | Filas antes | Filas después | Suma antes | Suma después |
|---|---:|---:|---|---|
| `applied_rates` | 0 | 0 | `d41d8cd9…7e` | `d41d8cd9…7e` |
| `closed_flight_snapshots` | 0 | 0 | `d41d8cd9…7e` | `d41d8cd9…7e` |
| `month_closings` | 0 | 0 | `d41d8cd9…7e` | `d41d8cd9…7e` |
| `flight_billing_adjustments` | 0 | 0 | `d41d8cd9…7e` | `d41d8cd9…7e` |
| `campaign_period_reviews` | 0 | 0 | `d41d8cd9…7e` | `d41d8cd9…7e` |
| `campaign_line_periods` con arrastre (`carryover > 0`) | 0 | 0 | `d41d8cd9…7e` | `d41d8cd9…7e` |
| `campaign_line_periods` | 14 | 14 | `f940b3d7…61` | `f940b3d7…61` |
| `daily_deliveries` | 127 | 127 | `a967938b…fe` | `a967938b…fe` |
| `ingestion_batches` | 3 | 3 | `41879301…cc` | `41879301…cc` |
| `alembic_version` | 1 (`f1c6d2b84a57`) | 1 (`f1c6d2b84a57`) | | |

La salida de las dos capturas es idéntica byte a byte (`cmp`). **Los tests no cambiaron nada y no hizo falta restaurar la base.**

## 14.2: ejecuciones

### Primero, los tests de las tareas 1 a 12

Son los 49 ficheros de test del backend nuevos o modificados desde la base del change (`git diff --diff-filter=AM c27e1fa HEAD -- backend/tests`), 14 de ellos nuevos:

```
pytest <los 49 ficheros> -q
1347 passed in 253.14s (0:04:13)
```

### Cinco suites, dos ejecuciones de cada una

| Suite | Comando | Ejecución 1 | Ejecución 2 |
|---|---|---|---|
| Backend completo | `pytest -q` (en `backend/`) | 3436 passed, 1 deselected, 0 skipped, 457,71 s | 3436 passed, 1 deselected, 0 skipped, 448,70 s |
| Aceptación de margen (43) | `pytest tests/acceptance tests/api/test_acceptance_closed_month_database.py tests/api/test_acceptance_running_month_database.py -q` | 43 passed, 8,96 s | 43 passed, 8,61 s |
| Vitest con typecheck | `npx vitest run` y `npm run typecheck` (en `frontend/`) | 71 ficheros, 743 passed, 38,15 s; tsc: 0 errores | 71 ficheros, 743 passed, 61,92 s; tsc: 0 errores |
| `node --test` de `e2e/` | los ficheros de `e2e/support/` y `e2e/scripts/` | 48 passed, 0 fail, 0 skipped | 48 passed, 0 fail, 0 skipped |
| `node --test` de la raíz | `node --test scripts/*.test.mjs` | 15 passed, 0 fail, 0 skipped | 15 passed, 0 fail, 0 skipped |

Después de la corrección de tipos de este paso, los cuatro ficheros que toca se ejecutaron de nuevo: 144 passed.

Notas:

- El «1 deselected» es el test marcado `slow`, que `pyproject.toml` excluye por defecto.
- Las 43 pruebas de aceptación corren y pasan, aparte y dentro de la suite completa: la hoja privada que las alimenta está presente.
- No hay fallos intermitentes: las dos ejecuciones de cada suite dan lo mismo.
- Playwright no se ejecutó aquí: es el paso 16. Su última ejecución, sobre datos limpios en el commit `9568e9a`, dio 46 passed.

### Comparación test a test con la base del change

Se recogieron los tests del backend en la base `c27e1fa` (2830), en un worktree temporal, y se compararon por identificador con los 3436 que pasan ahora. **Todos los de la base pasan ahora salvo 46, y ninguno de los 46 falla: cambiaron de nombre al invertirse o al cambiar su cifra.** Cada uno está en el informe del paso 13 o en `tasks.md`:

- **Del dominio, 23.** Los invertidos de la tarea 2.3: 14 en `test_flight_margin.py`, 3 en `test_priced_flights.py`, 2 en `test_margin_pct.py`, 2 en `test_contracted_revenue.py`, 1 en `test_rebate_counters.py` y 1 en `test_contracted_volume.py`. Las variantes parametrizadas cuentan aparte.
- **De aceptación contra las hojas, 13.** Los seis de la hoja cerrada y los siete de la hoja en curso comparan ahora con la hoja facturada al menor entre lo servido y lo contratado. Por ejemplo, `test_each_amount_of_each_row_matches_the_sheet` pasa a ser `…_matches_the_sheet_billed_at_the_lesser_of_served_and_contracted`.
- **De aceptación en base de datos, 2.** `test_only_the_flights_that_have_ended_are_closed` pasa a ser `test_closing_the_month_with_running_flights_is_refused_naming_them_and_writes_nothing`. `test_the_percentage_matches_the_actual_one_of_the_sheet` pasa a ser `…_matches_the_sheet_billed_to_date`.
- **De la API, 2.** Los vuelos en curso de `test_margin_end_to_end.py` y `test_margin_endpoint.py` ya no se prorratean.
- **De integración, 4.** En `test_margin_closing_service.py`, el vuelo en curso, el mes solo de Adform y la fila committed con su facturación. En `test_margin_repositories.py`, la fila committed.
- **El renombrado del paso 13** en `test_margin_schema.py`.
- **Un parámetro**, `test_margin_model_integrity.py::…[committed-3631.01]`, que ahora es `[committed-3500.00]`: el identificador lleva la cifra del ejemplo.

Suma: 23 + 13 + 2 + 2 + 4 + 1 + 1 = 46.

Del frontend y del E2E se midió lo mismo en la base, con los `node_modules` enlazados al worktree temporal:

| Suite | En `c27e1fa` | Ahora | Diferencia |
|---|---:|---:|---:|
| Backend, recogidas | 2830 | 3436 | +606 |
| Aceptación | 39 | 43 | +4: las dos de la diferencia conocida con cada hoja (grupo 3) y las dos de qué filas se apartan de ella |
| Vitest | 665 | 743 | +78: etiquetas de facturación, revisión antes del cierre, pantalla de facturación, arrastre en el estado, autor, mes por defecto y cliente compartido |
| `node --test` de `e2e/` | 48 | 48 | 0 |
| `node --test` de la raíz | 15 | 15 | 0 |
| E2E (`playwright test --list`) | 45 | 46 | +1: el botón «Cerrar mes» apagado mientras haya campañas pendientes de revisión |

### Backend: recogidas en cada commit del change

Medidas con `pytest --collect-only -q` en cada commit (el `deselected` aparte). Varios saltos incluyen las pruebas que recorren todos los módulos del dominio, de pureza y del guardián de la tarifa de plataforma: cada módulo nuevo les suma casos.

| Commit | Recogidas | Δ | Grupo |
|---|---:|---:|---|
| `c27e1fa` base | 2830 | | |
| `d05ed27` especificación | 2830 | 0 | |
| `a9991d2` rutas declaradas | 2900 | +70 | 0 y 1 |
| `d65b6e2` invariante del cierre | 2900 | 0 | |
| `255165a` la regla del menor | 2939 | +39 | 2 y 3 |
| `1ada142` marcas `pending-9.4` | 2939 | 0 | |
| `714fb40` columnas y reglas del arrastre | 2997 | +58 | 4 |
| `4c8837d` arrastre en el estado | 3010 | +13 | 5 |
| `e3db356` rutas del arrastre y la marca | 3072 | +62 | 6 |
| `e179f5a` ajustes | 3176 | +104 | 7 |
| `9cb4939` revisión mensual | 3271 | +95 | 8 |
| `7c63b59` cierre con revisión y foto de la facturación | 3349 | +78 | 9, con 11 y parte de 16 |
| `d6cb44a` lectura de la facturación y CSV | 3422 | +73 | 10 |
| `e0796b4` pantallas | 3422 | 0 | 12 (frontend y E2E) |
| `d58b801` autor visible | 3436 | +14 | 4 de la API; 2 de pureza y 8 del guardián por los dos módulos nuevos del dominio |
| `2a8bea1` mes por defecto | 3436 | 0 | frontend |
| `9568e9a` cliente compartido | 3436 | 0 | frontend |
| `1dbb441` informe del paso 13 | 3436 | 0 | cambia tests, no añade |

Suma de las diferencias: 3436 − 2830 = **606**.

### mypy

Con el comando de `docs/base-standards.md` §4, sobre los 114 ficheros Python del backend que el change toca (63 modificados y 51 nuevos), comparados con la base en un worktree temporal. Solo se cuentan los errores situados en esos ficheros. Se comparan por fichero y mensaje, sin el número de línea, que se desplaza con cada cambio.

| | En `c27e1fa` | Ahora |
|---|---:|---:|
| Errores en los 63 ficheros modificados | 502 | 502 |
| Errores que aparecen ahora y no en la base | | **0** |
| Errores de la base que ya no aparecen | | 0 |
| Errores en los 51 ficheros nuevos | | 16 |

**Corrección de este paso.** La primera comparación encontró cuatro errores nuevos que eran míos:

- un `# type: ignore[attr-defined]` innecesario en el `_on` de `test_billing_adjustments_endpoint.py`, `test_carryover_endpoint.py` y `test_monthly_review_endpoint.py`. Ninguno existía en la base; con el comando del proyecto sobran;
- el import de `TestClient` que el grupo 10 añadió a `test_margin_contracted_revenue.py` solo para tipar un fixture. Ahora el fixture se tipa con `Callable[..., Any]`.

Los 16 errores de los ficheros nuevos se deben todos a que mypy corre sin `fastapi` instalado:

- `import-not-found` de `fastapi` en los dos routers nuevos, y de `fastapi.testclient` en seis tests de API;
- los ocho «untyped decorator» de las rutas de esos dos routers, que se siguen del anterior.

El router del margen en la base da los mismos: `import-not-found` y un «untyped decorator» por ruta.

## Otros cambios de este paso

- `tasks.md` anota, como deuda fuera de este change, las nueve copias del cliente de la API que quedan en campañas (página y formulario), catálogo y excepciones.

## 14.4: estado de la tarea

Los tests del change y las cinco suites pasan dos veces. Cada test de la base pasa o está identificado por su nombre nuevo. mypy no añade ningún error en los ficheros del change. La base de desarrollo no cambió. Este informe existe. **El paso 14 queda completo.**
