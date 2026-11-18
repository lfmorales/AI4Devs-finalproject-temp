# Paso 14: tests unitarios y estado de la base de datos

**Fecha:** 2026-11-18
**Change:** `entra-auth-and-roles` (tarea 14.1)
**Commit:** `e635d05 docs: explain the adops360 compose project and worktrees`
**Rama:** `feature/entra-auth-and-roles`
**Ejecución:** `2026-11-18-1827` (evidencias en `docs/reports/2026-11-18-1827-*.txt`)

## Entorno

- **Backend:** Python 3.12, pytest contra una imagen `postgres:16` desechable con nombre propio, parada al terminar; la base de pruebas `adops360_test` se recrea al inicio de cada ejecución. Sin variables de autenticación en el entorno: `tests/conftest.py` fija valores de ejemplo de Entra.
- **Frontend:** Vitest y Testing Library, y `tsc --noEmit` (`npm run typecheck`), con Node.js v24.17.0.
- **Base de desarrollo:** la del stack de Compose de este worktree, que las suites no usan.
- **Datos privados:** la imagen no llevaba los ficheros de aceptación de los meses reales (`tests/private/`), así que esas pruebas se saltan.

## Estado de la base de desarrollo, antes

`2026-11-18-1827-db-antes.txt`: recuento de filas de cada tabla, usuarios activos, inactivos y vinculados, y la migración aplicada (users.active 7 inactive 0 linked 6, alembic_version e5d42817a180).

## Tests dirigidos

Los de identidad y acceso: protección de rutas, Entra obligatorio, emisor de pruebas, `GET /users/me`, autenticación a través de la aplicación, cableado de emisores, verificadores, proveedores de claves, contrato del repositorio de usuarios, concurrencia de la activación, migraciones de identidad y de roles, y configuración.

| Ejecución | Resultado |
|---|---|
| Identidad y acceso (`2026-11-18-1827-pytest-identity.txt`) | 386 passed, 29 warnings in 21.26s |

## Suites completas

### Backend (pytest)

| Ejecución | Resultado |
|---|---|
| 1 (`2026-11-18-1827-pytest-1.txt`) | 2210 passed, 38 skipped, 1 deselected, 68 warnings in 99.06s (0:01:39) |
| 2 (`2026-11-18-1827-pytest-2.txt`) | 2210 passed, 38 skipped, 1 deselected, 68 warnings in 119.76s (0:01:59) |

Las dos ejecuciones dan las mismas cifras: **2210 aprobadas, 38 saltadas, 1 excluida, 2248 recogidas**. Saltadas:

- 19: the private sheet mes_cerrado_directo.csv is not present in tests/private/ (it is ignored by git)
- 19: the private sheet mes_en_curso.csv is not present in tests/private/ (it is ignored by git)

La excluida es la prueba marcada `slow`, fuera de la ejecución por defecto.

### Frontend (Vitest)

| Ejecución | Ficheros | Tests | Duración |
|---|---|---|---|
| 1 | 61 passed (61) | 609 passed (609) | 34.72s |
| 2 | 61 passed (61) | 609 passed (609) | 32.81s |

### Verificación de tipos y scripts

| Comprobación | Resultado |
|---|---|
| `npm run typecheck` (frontend) | exit 0 (`2026-11-18-1827-typecheck.txt`) |
| `node --test` de `e2e` | 42 de 42, 0 fallidos (`2026-11-18-1827-node-test-e2e.txt`) |
| `node --test` de `scripts` | 15 de 15, 0 fallidos (`2026-11-18-1827-node-test-scripts.txt`) |
| `alembic current` del stack de desarrollo | `e5d42817a180 (head)` |
| `openspec validate entra-auth-and-roles` | Change 'entra-auth-and-roles' is valid |
| `scripts/verify_prod_images.sh` | OK: images built, /api/health 200 over HTTPS, port 80 redirects, backend image clean, without private keys and non-root, backend refuses the test issuer key, database not published, migrations applied as a separate step |

## Estado de la base de desarrollo, después

**Idéntico** al de antes (`2026-11-18-1827-db-despues.txt`): las suites usan su propia base, así que no hubo nada que restaurar.

| Tabla | Antes | Después |
|---|---:|---:|
| advertisers | 2 | 2 |
| agencies | 2 | 2 |
| alembic_version | 1 | 1 |
| applied_rate_brackets | 4 | 4 |
| applied_rates | 5 | 5 |
| campaign_line_periods | 18 | 18 |
| campaign_lines | 10 | 10 |
| campaign_periods | 18 | 18 |
| campaign_types | 4 | 4 |
| campaigns | 10 | 10 |
| channels | 4 | 4 |
| daily_deliveries | 61 | 61 |
| dsp_catalog_lines | 5 | 5 |
| dsp_mappings | 2 | 2 |
| dsps | 4 | 4 |
| formats | 4 | 4 |
| holding_groups | 2 | 2 |
| ingestion_batches | 2 | 2 |
| ingestion_exception_deliveries | 20 | 20 |
| ingestion_exceptions | 5 | 5 |
| platform_rate_settings | 2 | 2 |
| purchase_order_versions | 10 | 10 |
| purchase_orders | 10 | 10 |
| rebate_brackets | 3 | 3 |
| rebate_schedules | 2 | 2 |
| roles | 4 | 4 |
| sales_reps | 2 | 2 |
| sectors | 4 | 4 |
| user_roles | 10 | 10 |
| users | 7 | 7 |
