# Paso 17: tests unitarios y verificación de la base de datos

**Fecha:** 2026-11-20
**Change:** `ctv-and-delivery-metric` (tareas 17.1 a 17.4)
**Commit probado:** `1be678b docs(reports): paso 16, revisión de los tests del change`
**Rama:** `feature/ctv-and-delivery-metric`

## Entorno

- **Backend:** Python 3.12.16, contra un `postgres:16` desechable de nombre propio (PostgreSQL 16.15), parado y borrado al terminar. Los tests derivan de él su base de pruebas y ejecutan `alembic upgrade head`.
- **Frontend y scripts:** Node 24.17.0 (`nvm use 24`; el proyecto pide `>=22`).
- **Base de desarrollo:** la del stack Compose de este worktree. Ningún test la usa; se vigila para comprobarlo.

## 17.1 y 17.3: base de desarrollo antes y después

Conteo y suma de comprobación (`md5` del texto de las filas ordenadas por `id`) de las cinco tablas que toca el change. El estado de partida es el que dejó la última ejecución E2E sobre datos recién sembrados.

| Tabla | Filas antes | Filas después | Suma antes | Suma después |
|---|---:|---:|---|---|
| `channels` | 5 | 5 | `d3d5897b…ff` | `d3d5897b…ff` |
| `daily_deliveries` | 71 | 71 | `c08af403…74` | `c08af403…74` |
| `rebate_schedules` | 3 | 3 | `d22d2436…4e` | `d22d2436…4e` |
| `campaigns` | 11 | 11 | `fa543211…5a` | `fa543211…5a` |
| `ingestion_exceptions` | 5 | 5 | `3b1af9a9…f5` | `3b1af9a9…f5` |
| `alembic_version` | 1 (`8010208e4c15`) | 1 (`8010208e4c15`) | | |

La salida de las dos capturas es idéntica byte a byte. **Los tests no cambiaron nada y no hizo falta restaurar la base** con `reset-data.sh`.

## 17.2: ejecuciones

### Tests de las tareas 1 a 15, primero

Los 43 ficheros de test nuevos o modificados desde el spec (`git diff --diff-filter=AM 1272c4e HEAD -- tests`):

```
pytest <los 43 ficheros> -q
670 passed, 61 warnings in 60.12s (0:01:00)
```

### Cinco suites, dos ejecuciones de cada una

| Suite | Comando | Ejecución 1 | Ejecución 2 |
|---|---|---|---|
| Backend completo | `pytest -q` (en `backend/`) | 2418 passed, 1 deselected, 0 skipped, 121,01 s | 2418 passed, 1 deselected, 0 skipped, 91,21 s |
| Aceptación de margen (38) | `pytest tests/acceptance tests/api/test_acceptance_closed_month_database.py tests/api/test_acceptance_running_month_database.py -q` | 38 passed, 4,34 s | 38 passed, 4,41 s |
| Vitest con typecheck | `npx vitest run` y `npx tsc --noEmit` (en `frontend/`) | 61 ficheros, 622 passed, 30,85 s; tsc: 0 errores | 61 ficheros, 622 passed, 32,69 s; tsc: 0 errores |
| `node --test` de `e2e/` | los cuatro ficheros de `e2e/support/` y `e2e/scripts/` | 46 passed, 0 fail, 0 skipped | 46 passed, 0 fail, 0 skipped |
| `node --test` de la raíz | `node --test scripts/*.test.mjs` (en la raíz del repositorio) | 15 passed, 0 fail, 0 skipped | 15 passed, 0 fail, 0 skipped |

Notas:

- Los 38 saltados que había antes por falta de las hojas privadas ya no existen: `backend/tests/private/` tiene los dos CSV (ignorados por Git) y las 38 pruebas de aceptación corren y pasan, tanto aparte como dentro de la suite completa.
- El «1 deselected» es el test marcado `slow`, que `pyproject.toml` excluye por defecto (`-m 'not slow'`).
- Por fichero de `node --test` de `e2e/`: `campaigns.test.mjs` 4, `compose-project.test.mjs` 12, `test-issuer.test.mjs` 16 y `reset-data.test.mjs` 14. Por fichero de la raíz: `scripts/compose-project-name.test.mjs` 8 y `scripts/generate_test_issuer_keys.test.mjs` 7. `git ls-files '*.test.mjs' '*.test.js'` lista esos seis ficheros y ninguno más fuera de `frontend/` (que usa Vitest).
- Sin fallos intermitentes: las dos ejecuciones de cada suite dan lo mismo.
- No se ejecutó el E2E de Playwright aquí: es el paso 19.

## Reconciliación con el cierre del change anterior

Referencia: el commit `3ef28db` (archivo de `entra-auth-and-roles`), medido de nuevo en un worktree temporal con los mismos comandos, no tomado de memoria.

| Suite | En `3ef28db` | Ahora | Diferencia | Origen |
|---|---:|---:|---:|---|
| Backend, recogidas | 2248 | 2418 | +170 | tabla siguiente |
| Vitest | 609 | 622 | +13 | grupo 14: 4 de `formatQuantity`, 3 de estado, 3 de leyenda de margen, 2 de leyenda en `messages.test.ts` y 1 de `mixed_delivery_metrics` |
| E2E (`playwright test --list`) | 40 | 42 | +2 | grupo 15: uno en `status.spec.ts` y uno en `margin.spec.ts` |
| `node --test` de `e2e/` | 42 (12 + 16 + 14) | 46 | +4 | grupo 15: `campaigns.test.mjs` |
| `node --test` de la raíz (`scripts/`) | 15 (8 + 7) | 15 | 0 | el change no los toca |

Las cifras con las que se cerró el change anterior se reproducen exactamente en `3ef28db`:

- **2.248** recogidas en backend y **609** en Vitest.
- **40** de Playwright y **42** de `node --test` de `e2e/`.
- **15** de scripts, que son los dos ficheros de la raíz (`scripts/compose-project-name.test.mjs`, 8, y `scripts/generate_test_issuer_keys.test.mjs`, 7), contados aparte de los de `e2e/`. Ejecutados en `3ef28db` y ahora dan 15 de 15 en los dos casos.

No queda ninguna discrepancia sin resolver. Una versión anterior de este informe daba 42 como cifra de E2E de `3ef28db` y 15 como los tests de `reset-data.test.mjs`: eran dos cifras de otras suites, y las de arriba son las medidas.

Nota para repetir la medida de `3ef28db` en un worktree temporal: `generate_test_issuer_keys.test.mjs` falla un caso («development mounts only the public directory…») si la ruta del worktree contiene la palabra `private`, como las de `$TMPDIR` en macOS (`/private/var/...`), porque el test busca esa palabra entre las rutas montadas. No es una regresión: con el worktree en una ruta sin esa palabra los 7 casos pasan.

### Backend: recogidas en cada commit del change

Medidas con `pytest --collect-only -q` en cada commit (el `deselected` aparte):

| Commit | Recogidas | Δ | Grupo |
|---|---:|---:|---|
| `1272c4e` spec | 2248 | | |
| `dd326b7` canales Directo, Deal, DOOH y CTV | 2254 | +6 | 1 |
| `4e69b21` escala sin canal por grupo, agencia, canal y ámbito | 2255 | +1 | 1 |
| `d3c51b9` petición a Adform | 2257 | +2 | 2 |
| `3433d9a` lectura de `ots` y completados | 2286 | +29 | 3 |
| `8c18079` combinación de filas | 2290 | +4 | 4 |
| `454ff5f` columnas de entregas diarias | 2300 | +10 | 5 |
| `b197b11` documentación de mypy | 2300 | 0 | |
| `7a58dcd` fila sin línea con solo OTS | 2302 | +2 | 6 |
| `e1bd7ea` métrica por canal | 2337 | +35 | 7 |
| `0870872` una métrica por campaña | 2347 | +10 | 8 |
| `51738e2` nota de la tarea 14.3 | 2347 | 0 | |
| `ba5f50b` estado | 2354 | +7 | 9 |
| `33cea46` ritmo | 2362 | +8 | 10 |
| `8c1e9da` aceptación con `operations` | 2362 | 0 | |
| `58b74a5` margen y cierre | 2385 | +23 | 11 (21 más 2 del esquema nulo) |
| `15d0ab7` hechos del vuelo obligatorios | 2385 | 0 | |
| `14d2453` línea sin entrega | 2390 | +5 | 12 |
| `8cdf219` nota de despliegue | 2390 | 0 | |
| `ee00258` esquemas de la API | 2410 | +20 | 13 (18 de los tres ficheros de test más 2 de la guarda de `quantity.py`) |
| `4ce4252` pantallas | 2410 | 0 | 14 (frontend) |
| `b3fba63` demostración DOOH | 2418 | +8 | 15 |
| `1be678b` informe del paso 16 | 2418 | 0 | |

Suma de las diferencias: 2418 − 2248 = **170**.

Las cifras de los informes por grupo de la conversación de trabajo se dieron a veces con y a veces sin el test deseleccionado; esta tabla las unifica, todas sin él.

## 17.4: estado de la tarea

Las cinco suites pasan dos veces, la base de desarrollo no cambió y este informe existe: el paso 17 queda completo.
