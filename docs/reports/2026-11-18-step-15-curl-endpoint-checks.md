# Paso 15: comprobación de los endpoints con curl

**Fecha:** 2026-11-18
**Change:** `entra-auth-and-roles` (tarea 15.1)
**Commit:** `e635d05 docs: explain the adops360 compose project and worktrees`
**Stack:** el de desarrollo de este worktree (`http://localhost/api`), con datos recién sembrados (`e2e/scripts/reset-data.sh`) y los usuarios E2E sembrados con la misma SQL que el *global setup* (`e2e/support/e2e-users.ts`).

## Cómo se hizo

- Un script local firma en memoria, en cada ejecución, un token del emisor de pruebas por petición (RS256 con la clave privada de `.secrets/test-issuer/`, que no está en el repositorio), con la forma de los de Entra: `iss` y audiencia del emisor de pruebas, `ver` 2.0, `scp` `access_as_user`, `oid` y `email` del usuario E2E, diez minutos de vida.
- curl lee la cabecera `Authorization` de su entrada estándar (`-K -`): ningún token se escribe en disco, en un fichero de evidencia ni en la lista de procesos.
- Casos de autenticación: sin token; un token firmado con otra clave RSA generada en el momento; un `iss` que no está configurado; y un usuario que no existe en la base (`nadie@adops360.example.test`).
- Matriz: cada ruta cuyo acceso cambió respecto a `5b8ee60` (el punto donde la rama se separa de `final-project-LFMC`), con un perfil que ya no la tiene o nunca la tuvo (403) y otro que la gana (2xx). `GET /campaign-status` está abierto ahora a los cuatro roles, así que no hay perfil E2E sin acceso; se comprueba con los dos que lo ganan (finance y trading).
- Interruptor de activo: operations desactiva al usuario `e2e-trading`, su siguiente petición da 403 `user_inactive`, se reactiva y vuelve a dar 200 con el mismo tipo de token.

## Resultado: requests 50 matching 50 different 0

| # | Método | Ruta | Perfil | Esperado | Obtenido | Código del cuerpo |
|---:|---|---|---|---:|---:|---|
| 1 | GET | `/users/me` | sin token | 401 | 401 | `unauthenticated` |
| 2 | GET | `/users/me` | operations, firmado con otra clave | 401 | 401 | `unauthenticated` |
| 3 | GET | `/users/me` | operations, iss desconocido | 401 | 401 | `unauthenticated` |
| 4 | GET | `/users/me` | no registrado (nadie@adops360.example.test) | 403 | 403 | `user_not_registered` |
| 5 | GET | `/users/me` | operations | 200 | 200 |  |
| 6 | GET | `/users/me` | business | 200 | 200 |  |
| 7 | GET | `/users/me` | finance | 200 | 200 |  |
| 8 | GET | `/users/me` | trading | 200 | 200 |  |
| 9 | GET | `/users/me` | finance-trading | 200 | 200 |  |
| 10 | GET | `/users/me` | business-trading | 200 | 200 |  |
| 11 | GET | `/campaigns` | trading | 403 | 403 | `missing_role` |
| 12 | GET | `/campaigns` | finance | 200 | 200 |  |
| 13 | GET | `/masters/agencies` | trading | 403 | 403 | `missing_role` |
| 14 | GET | `/masters/agencies` | finance | 200 | 200 |  |
| 15 | GET | `/masters/advertisers` | trading | 403 | 403 | `missing_role` |
| 16 | GET | `/masters/advertisers` | finance | 200 | 200 |  |
| 17 | GET | `/masters/dsps` | trading | 403 | 403 | `missing_role` |
| 18 | GET | `/masters/dsps` | finance | 200 | 200 |  |
| 19 | GET | `/masters/dsps` | business | 200 | 200 |  |
| 20 | GET | `/masters/channels` | trading | 403 | 403 | `missing_role` |
| 21 | GET | `/masters/channels` | finance | 200 | 200 |  |
| 22 | GET | `/masters/channels` | business | 200 | 200 |  |
| 23 | GET | `/masters/formats` | trading | 403 | 403 | `missing_role` |
| 24 | GET | `/masters/formats` | finance | 200 | 200 |  |
| 25 | GET | `/masters/formats` | business | 200 | 200 |  |
| 26 | GET | `/masters/campaign-types` | trading | 403 | 403 | `missing_role` |
| 27 | GET | `/masters/campaign-types` | finance | 200 | 200 |  |
| 28 | GET | `/masters/campaign-types` | business | 200 | 200 |  |
| 29 | GET | `/masters/sectors` | trading | 403 | 403 | `missing_role` |
| 30 | GET | `/masters/sectors` | finance | 200 | 200 |  |
| 31 | GET | `/masters/sectors` | business | 200 | 200 |  |
| 32 | GET | `/masters/sales-reps` | trading | 403 | 403 | `missing_role` |
| 33 | GET | `/masters/sales-reps` | finance | 200 | 200 |  |
| 34 | GET | `/masters/sales-reps` | business | 200 | 200 |  |
| 35 | GET | `/campaign-status` | trading | 200 | 200 |  |
| 36 | GET | `/campaign-status` | finance | 200 | 200 |  |
| 37 | GET | `/margin?year=2026&month=10` | business | 403 | 403 | `missing_role` |
| 38 | GET | `/margin?year=2026&month=10` | trading | 403 | 403 | `missing_role` |
| 39 | GET | `/margin?year=2026&month=10` | operations | 200 | 200 |  |
| 40 | POST | `/margin/closings` | business | 403 | 403 | `missing_role` |
| 41 | POST | `/margin/closings` | operations | 200 | 200 |  |
| 42 | POST | `/margin/rebate-schedules` | finance | 403 | 403 | `missing_role` |
| 43 | POST | `/margin/rebate-schedules` | operations | 201 | 201 |  |
| 44 | POST | `/margin/platform-rates` | finance | 403 | 403 | `missing_role` |
| 45 | POST | `/margin/platform-rates` | operations | 201 | 201 |  |
| 46 | POST | `/users/activation` | finance | 403 | 403 | `missing_role` |
| 47 | POST | `/users/activation` | operations (desactiva a e2e-trading) | 200 | 200 |  |
| 48 | GET | `/users/me` | trading, desactivado | 403 | 403 | `user_inactive` |
| 49 | POST | `/users/activation` | operations (reactiva a e2e-trading) | 200 | 200 |  |
| 50 | GET | `/users/me` | trading, reactivado | 200 | 200 |  |

La salida completa está en `2026-11-18-1827-curl.txt`.

## Estado de la base

- **Antes** (`2026-11-18-1827-db-antes-curl.txt`): datos recién sembrados, los usuarios E2E sin vincular (users.active 7 inactive 0 linked 0, alembic_version e5d42817a180).
- **Después de las peticiones** (`2026-11-18-1827-db-despues-curl.txt`): un mes cerrado, una escala de extraprima y una tarifa de plataforma nuevas (las respuestas 2xx de las escrituras), y seis usuarios vinculados en su primer acceso (users.active 7 inactive 0 linked 6, alembic_version e5d42817a180).
- **Restaurada** (`2026-11-18-1827-db-restaurada-curl.txt`) con `e2e/scripts/reset-data.sh` y la misma siembra de usuarios E2E: **idéntica** a la de antes.

| Tabla | Antes | Después de las peticiones |
|---|---:|---:|
| advertisers | 2 | 2 |
| agencies | 2 | 2 |
| alembic_version | 1 | 1 |
| applied_rate_brackets | 0 | 3 |
| applied_rates | 0 | 3 |
| campaign_line_periods | 11 | 11 |
| campaign_lines | 6 | 6 |
| campaign_periods | 11 | 11 |
| campaign_types | 4 | 4 |
| campaigns | 6 | 6 |
| channels | 4 | 4 |
| daily_deliveries | 61 | 61 |
| dsp_catalog_lines | 5 | 5 |
| dsp_mappings | 1 | 1 |
| dsps | 4 | 4 |
| formats | 4 | 4 |
| holding_groups | 2 | 2 |
| ingestion_batches | 2 | 2 |
| ingestion_exception_deliveries | 20 | 20 |
| ingestion_exceptions | 5 | 5 |
| platform_rate_settings | 2 | 3 |
| purchase_order_versions | 6 | 6 |
| purchase_orders | 6 | 6 |
| rebate_brackets | 3 | 4 |
| rebate_schedules | 2 | 3 |
| roles | 4 | 4 |
| sales_reps | 2 | 2 |
| sectors | 4 | 4 |
| user_roles | 10 | 10 |
| users | 7 | 7 |

Una primera ejecución, también sobre datos recién sembrados, dio 49 de 50: `POST /margin/rebate-schedules` con operations respondió 409 `schedule_overlaps_existing` porque la escala de prueba se solapaba con una sembrada (la autorización ya había pasado). Se cambió la escala de prueba a una por canal y se repitió todo desde datos limpios; la tabla de arriba es esa segunda ejecución.
