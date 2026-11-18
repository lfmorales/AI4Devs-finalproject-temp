# Paso 13: revisión de los tests que nombran un rol

**Fecha:** 2026-11-18
**Change:** `entra-auth-and-roles` (tarea 13.1)
**Commit revisado:** `e635d05 docs: explain the adops360 compose project and worktrees`
**Rama:** `feature/entra-auth-and-roles`

## Qué se revisó

Los tests que nombran un rol, con la búsqueda que pide la tarea (`RoleName` y los cuatro nombres de rol como palabra completa):

```
git grep -l -P "RoleName|\b(operations|business|finance|trading)\b" -- backend/tests e2e frontend/tests
```

**53 ficheros** (36 de `backend/tests`, 7 de `e2e` y 10 de `frontend/tests`) con **392 coincidencias**. La lista está en `2026-11-18-1827-role-test-files.txt`.

La columna «Estado en la rama» compara cada fichero con el commit `5b8ee60` («docs(readme): link pull request 3 from sections 0.5 and 7», 2026-11-09), el punto donde esta rama se separa de `final-project-LFMC` (`git merge-base HEAD final-project-LFMC`): **17 nuevos**, **22 modificados** y **14 sin cambios**. Los nuevos y los modificados son los que el change creó o adaptó a la matriz en sus tareas (7 a 12 y 21); los que no cambian nombran roles cuyo acceso la matriz no tocó, o los usan solo para preparar datos.

| Fichero | Coincidencias | Estado en la rama |
|---|---:|---|
| `backend/tests/api/conftest.py` | 11 | sin cambios |
| `backend/tests/api/test_acceptance_closed_month_database.py` | 18 | sin cambios |
| `backend/tests/api/test_acceptance_running_month_database.py` | 20 | sin cambios |
| `backend/tests/api/test_auth_dependencies.py` | 11 | sin cambios |
| `backend/tests/api/test_campaign_registration.py` | 4 | modificado |
| `backend/tests/api/test_campaign_status_endpoint.py` | 3 | modificado |
| `backend/tests/api/test_dsp_catalog_endpoint.py` | 1 | sin cambios |
| `backend/tests/api/test_dsp_mapping_endpoint.py` | 1 | sin cambios |
| `backend/tests/api/test_identity_authentication_api.py` | 15 | nuevo |
| `backend/tests/api/test_ingestion_exceptions_endpoints.py` | 1 | sin cambios |
| `backend/tests/api/test_margin_closings_endpoint.py` | 5 | modificado |
| `backend/tests/api/test_margin_coherence.py` | 1 | sin cambios |
| `backend/tests/api/test_margin_contracted_revenue.py` | 1 | sin cambios |
| `backend/tests/api/test_margin_end_to_end.py` | 20 | modificado |
| `backend/tests/api/test_margin_endpoint.py` | 5 | modificado |
| `backend/tests/api/test_margin_masters_endpoints.py` | 4 | modificado |
| `backend/tests/api/test_margin_zero_sale.py` | 2 | sin cambios |
| `backend/tests/api/test_route_protection.py` | 11 | modificado |
| `backend/tests/api/test_seed_exceptions_demo_endpoints.py` | 21 | sin cambios |
| `backend/tests/api/test_seed_margin_demo_states.py` | 1 | sin cambios |
| `backend/tests/api/test_unmapped_lines_endpoint.py` | 1 | sin cambios |
| `backend/tests/api/test_user_activation_endpoint.py` | 34 | nuevo |
| `backend/tests/api/test_users_me_endpoint.py` | 13 | nuevo |
| `backend/tests/application/test_authentication_by_identity.py` | 3 | nuevo |
| `backend/tests/application/test_authentication_service.py` | 6 | modificado |
| `backend/tests/domain/test_role_name.py` | 2 | nuevo |
| `backend/tests/fixtures/fake_adform.py` | 1 | sin cambios |
| `backend/tests/fixtures/identity.py` | 3 | modificado |
| `backend/tests/fixtures/master_data.py` | 5 | modificado |
| `backend/tests/infrastructure/test_four_roles_migration.py` | 6 | nuevo |
| `backend/tests/infrastructure/test_issuer_token_verifier.py` | 1 | nuevo |
| `backend/tests/infrastructure/test_trading_role_migration.py` | 10 | nuevo |
| `backend/tests/infrastructure/test_user_activation_concurrency.py` | 2 | nuevo |
| `backend/tests/infrastructure/test_user_repository_contract.py` | 15 | nuevo |
| `backend/tests/scripts/test_grant_roles.py` | 20 | modificado |
| `backend/tests/scripts/test_seed_dev_data.py` | 9 | modificado |
| `e2e/scripts/reset-data.test.mjs` | 2 | modificado |
| `e2e/support/e2e-users.ts` | 10 | nuevo |
| `e2e/support/fixtures.ts` | 5 | modificado |
| `e2e/support/global-setup.ts` | 2 | modificado |
| `e2e/support/test-issuer.test.mjs` | 12 | nuevo |
| `e2e/tests/navigation-roles.spec.ts` | 3 | modificado |
| `e2e/tests/roles-matrix.spec.ts` | 14 | nuevo |
| `frontend/tests/unit/app/buttons-by-roles.test.tsx` | 12 | nuevo |
| `frontend/tests/unit/app/dsp-catalog/catalogue-page.test.tsx` | 1 | modificado |
| `frontend/tests/unit/app/exceptions/exceptions-page.test.tsx` | 1 | modificado |
| `frontend/tests/unit/app/home-by-roles.test.tsx` | 5 | nuevo |
| `frontend/tests/unit/app/home.test.tsx` | 2 | modificado |
| `frontend/tests/unit/app/margin/margin-access.test.tsx` | 1 | modificado |
| `frontend/tests/unit/app/navigation-by-profile.test.tsx` | 11 | nuevo |
| `frontend/tests/unit/app/navigation-by-roles.test.tsx` | 21 | nuevo |
| `frontend/tests/unit/app/navigation-current.test.tsx` | 2 | modificado |
| `frontend/tests/unit/lib/api/client.test.ts` | 1 | modificado |

## La matriz de acceso

La matriz de la especificación `identity/access-matrix` coincide con `ACCESS_MATRIX` de `backend/tests/api/test_route_protection.py`, y ese test comprueba, ruta a ruta, que los `require_roles` de los routers dicen lo mismo y que no hay rutas sin entrada ni entradas sin ruta:

| Rutas (especificación) | Roles | Entradas de `ACCESS_MATRIX` |
|---|---|---|
| Lecturas de campañas y maestros | operations, business, finance | `GET /campaigns`, `GET /masters/*` (8) → `READERS` |
| Escrituras de campañas y maestros | operations | `POST /campaigns` → `OPERATIONS` |
| Estado de entrega | operations, business, finance, trading | `GET /campaign-status` → `EVERYONE` |
| Excepciones, mapeos, catálogo, previsualización, líneas sin mapear | operations | 7 entradas → `OPERATIONS` |
| `GET /margin` y `POST /margin/closings` | operations, finance | → `MARGIN_READERS` |
| `POST /margin/rebate-schedules` y `POST /margin/platform-rates` | operations | → `OPERATIONS` |
| `POST /users/activation` | operations | → `OPERATIONS` |
| `GET /users/me` | los cuatro | → `EVERYONE` |

El frontend (`frontend/lib/auth/navigation.ts`, `NAVIGATION_LINKS`) y los E2E (`e2e/tests/roles-matrix.spec.ts`, `OPENS`) llevan la misma matriz por página: Campañas para operations, business y finance; Estado para los cuatro; Margen para operations y finance; Excepciones y Catálogo Adform solo para operations.

## Resultado

No hizo falta cambiar ningún test en esta revisión: los afectados por la matriz ya se adaptaron en sus tareas. `backend/tests/api/test_route_protection.py` y el resto de tests de identidad pasan (386 aprobados, `2026-11-18-1827-pytest-identity.txt`), y la suite completa también (paso 14).
