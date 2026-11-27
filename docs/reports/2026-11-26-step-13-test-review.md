# Paso 13: revisión de los tests cuyo significado cambió

**Fecha:** 2026-11-26
**Change:** `committed-billing-and-review` (tarea 13.1)
**Commit revisado:** `9568e9a refactor(frontend): the margin page takes the shared API client`
**Rama:** `feature/committed-billing-and-review`

## Qué se revisó

Todos los tests que el change tocó, desde su base (`c27e1fa`, el padre del commit de la especificación `d05ed27`):

```
git diff --name-status c27e1fa HEAD -- backend/tests frontend/tests e2e
```

**77 ficheros**: 20 nuevos y 57 modificados. Esta revisión se centra en los modificados cuyo significado cambió: un test que afirmaba lo contrario, o que afirmaba lo mismo con otra cifra, por la regla nueva. Los nuevos prueban comportamiento nuevo y se revisaron en el grupo que los creó, con su rojo.

La regla que mueve casi todos: **un vuelo committed factura el menor entre lo entregado y su tope** (lo contratado, más el arrastre si es facturable), salvo un ajuste en vigor. Antes devengaba toda la venta contratada al cerrar y la prorrateaba por días mientras corría. El ejemplo de trabajo, 700.000 entregadas de 1.000.000 contratadas a 5,00 €, pasa de 5.000,00 € a 3.500,00 €.

## Tests del dominio invertidos en la tarea 2.3

| Fichero | Antes | Ahora | Razón |
|---|---|---|---|
| `test_flight_margin.py` | `test_under_delivery_does_not_reduce_revenue` | `test_under_delivery_reduces_revenue_to_the_billing` | Invertido: la entrega por debajo de lo contratado reduce la facturación. |
| `test_flight_margin.py` | `test_revenue_is_the_same_whatever_was_delivered` | `test_revenue_is_the_lesser_of_delivered_and_contracted` | Invertido, parametrizado por entrega. |
| `test_flight_margin.py` | `test_a_running_flight_is_pro_rated_by_elapsed_days_of_its_window` | `test_a_running_flight_bills_its_delivery_to_date` | Sin prorrateo: 180.000 entregadas a 5,00 € son 900,00 €, no 5.000 × 10 / 31 = 1.612,90 €. |
| `test_flight_margin.py` | `test_a_running_flight_with_no_delivery_still_accrues_revenue` | `test_a_running_flight_with_no_delivery_earns_nothing` | Invertido. |
| `test_flight_margin.py` | `test_pro_rating_does_not_depend_on_what_was_delivered` | `test_a_running_flight_s_billing_follows_its_delivery_up_to_its_cap` | Invertido. |
| `test_flight_margin.py` | `test_a_pro_rated_amount_is_rounded_once_after_pro_rating` | `test_a_billing_to_date_is_rounded_once_half_up` | Mismo redondeo, sobre la facturación. |
| `test_flight_margin.py` | `test_a_closed_dooh_flight_earns_the_revenue_of_its_contracted_ots` | `test_a_closed_dooh_flight_bills_its_delivered_ots` | Invertido: 280.000,50 OTS de 300.000 facturan 1.400,00 €. |
| `test_flight_margin.py` | `test_a_running_committed_flight_is_still_pro_rated_whatever_is_reported` | `test_a_running_committed_flight_bills_its_delivery_whatever_is_reported` | Lo que comunica el DSP sigue sin contar para un vuelo committed. |
| `test_flight_margin.py` | `test_the_rebate_base_of_a_committed_flight_is_its_contracted_revenue` | `test_the_rebate_base_of_a_committed_flight_is_its_billing` | La base del rebate es la facturación. |
| `test_priced_flights.py` | `test_the_counter_is_fed_with_the_rounded_revenue_of_the_flight` | `…_rounded_billing_of_the_flight` | El contador avanza con la facturación. |
| `test_priced_flights.py` | `test_a_running_flight_is_pro_rated_by_the_margin_and_reads_the_full_rebate` | `test_a_running_flight_is_priced_on_its_billing_to_date_and_nothing_is_pro_rated` | Ni la facturación ni el rebate se prorratean. |
| `test_priced_flights.py` | `test_a_committed_flight_still_accrues_its_contracted_revenue_whatever_it_reports` | `test_a_committed_flight_still_bills_its_delivery_whatever_it_reports` | Igual que el anterior de `test_flight_margin.py`. |
| `test_rebate_counters.py` | `test_the_margin_prorates_a_running_flights_full_rebate_by_elapsed_days` | `test_a_running_flight_is_charged_on_its_billing_to_date_and_its_rebate_is_not_pro_rated` | Invertido. |
| `test_margin_pct.py` | `test_the_worked_example_is_22_67_points` y `…_pro_rated_figures` | `…_20_71_points` y `…_billing_to_date` | El ejemplo de trabajo factura 3.500,00 €: su margen es 725,00 € y su porcentaje 20,71. |
| `test_contracted_volume.py` | `test_revenue_from_contracted_not_delivered` | `test_the_contracted_sale_reads_the_contracted_volume_not_the_delivery` | **No invertido**, como decía la tarea 2.3: `ContractedVolume` no tiene entrega y su cifra es la venta contratada. Solo cambió el nombre, que decía «revenue». |

Dos ficheros siguen afirmando lo mismo, con otros datos:

- `test_margin_totals.py`: que los totales suman sus vuelos. Su vuelo por defecto entrega ahora lo que contrató. El ejemplo de trabajo de sus totales factura 3.500,00 €, así que las sumas esperadas pasan de 3.641,01 a 3.510,00 € de ingreso y de 829,76 a 731,50 € de margen. El vuelo en curso entrega 1.000 de 3.000 en lugar de prorratearse.
- `test_zero_sale.py`: que el vuelo con precio de su par alimenta el contador. Ahora entrega sus 6.000.000 para facturar su venta.

## Los demás ficheros que nombra la tarea

| Fichero | Qué cambió | Razón |
|---|---|---|
| `test_contracted_revenue.py:38` | Un vuelo en curso con 180.000 entregadas tiene `revenue` 900,00 € y sigue con toda su venta contratada, 5.000,00 €, y 10 de 31 días. | La venta contratada no cambia; el devengo prorrateado pasa a ser la facturación hasta ayer. El comentario del test lo dice. Se añadió `…_under_delivered_bills_less_than_its_contracted_sale` (3.500,00 frente a 5.000,00). |
| `test_closed_flight.py`: el ejemplo committed | La foto del vuelo de 700.000 de 726.202 guarda `revenue` 3.500,00 y margen 725,00, antes 3.631,01 y 823,26. | La facturación. Desde el grupo 9 la foto guarda también la base, el volumen facturable, el arrastre y su marca, y compara márgenes enteros: el ayudante provisional `_without_billing` ya no existe. |
| `test_closed_flight.py`: la foto DOOH | `revenue` 1.400,00 (280.000,50 OTS) y margen 1.388,00, antes 1.500,00 y 1.488,00. | El vuelo DOOH factura sus OTS entregadas. |
| `test_closed_flight.py`: el aviso | El ejemplo reexpresado da margen actual −75,00 € y diferencia −800,00 €, con +300.000 facturables y +1.500,00 € de facturación. Tras desvincular la línea da −875,00 €. | El aviso compara con la facturación actual. La foto anterior al change (`_closed_committed`) sigue dando −450,00 € con su ingreso congelado, y sus diferencias de facturación son nulas. |
| `test_priced_flights.py` | Ver la tabla anterior. | |
| `test_margin_contracted_revenue.py:55` | Vuelo en curso de la API: `revenue` 900,00, no 1.612,90. | Igual que en el dominio. |
| `test_margin_contracted_revenue.py:68` | Un vuelo pendiente de cierre o cerrado factura toda su venta solo si entregó todo lo contratado: el test lo prepara con 1.000.000 entregadas. | Antes devengaba toda la venta con cualquier entrega. |
| `test_margin_coherence.py` | Cada línea entrega lo que contrató, así el contador recibe 30.000, 60.000 y 30.000 € como antes. El escenario revisa julio y agosto antes de cerrarlos. | La facturación y la revisión. |
| `test_margin_end_to_end.py` | El ejemplo factura 3.500,00 € (700.000 de 726.202), con margen 725,00 €. Revisa antes de cerrar. | La facturación y la revisión. |
| `test_margin_endpoint.py` | Vuelo en curso a 900,00 €. Cada cierre revisa antes. | La facturación y la revisión. |
| `test_margin_zero_sale.py` | La línea con precio factura 3.500,00 €. El fixture revisa agosto. | La facturación y la revisión. |
| `test_margin_delivery_change_endpoint.py` | Margen actual −75,00 € y diferencia −800,00 €, con `billable_difference` y `billing_difference` en la respuesta (null para el vuelo objetivo). Revisa antes de cerrar. | El aviso compara con la facturación actual; las marcas `pending-9.4` ya no existen. |
| `test_margin_closings_endpoint.py` | El montaje revisa antes de cerrar. Dos casos nuevos de `month_not_reviewed`, con su mensaje exacto. | El cierre exige la revisión. |
| `test_seed_margin_demo_states.py` | El fixture revisa septiembre con `load_last_day=False`, así el test sigue comprobando que el último día lo carga la propia semilla. | El cierre exige la revisión y el último día de cada DSP. |
| `tests/scripts/test_run_ingestion*.py` | **Nada.** | Su `close_month` no ejecuta el cierre: escribe una cabecera en `month_closings`, que es lo único que mira la ingesta. Como no cierra por el servicio, no tiene revisión que hacer. La tarea decía «all review first»: no aplica a estos tres. |
| `test_frozen_revenue_migration.py` | Fija `AFTER = "950895fa2d75"`. | Sus migraciones posteriores no forman parte del test. Sigue verde con la cabeza nueva. |
| `test_closing_snapshot_migration.py` | Fija `AFTER = "3a08cce1c979"`. | Igual que el anterior. La migración nueva de la foto (`f1c6d2b84a57`) tiene su propio test, `test_billing_snapshot_migration.py`. |
| `test_margin_schema.py` | **Cambiado en esta revisión.** La comprobación de que ninguna columna de las tablas del margen es de coma flotante no incluía las dos tablas nuevas: ahora cubre `flight_billing_adjustments`, que guarda un importe, y `campaign_period_reviews`. `test_a_committed_flights_row_holds_neither_frozen_amount` pasa a llamarse `test_a_row_may_hold_neither_frozen_amount_as_a_committed_row_closed_before_the_billing_was_frozen`. | El nombre decía lo que ya no hace el cierre: desde el grupo 9 una fila committed guarda su facturación en las dos columnas. El esquema sigue admitiendo las dos vacías para las filas anteriores, que es lo que el test prueba. Ampliar la lista es una red de seguridad: pasa sin cambiar código, y un nombre de tabla mal escrito haría fallar `get_columns`. |
| `frontend/tests/helpers/margin-data.ts` | `flight()` lleva `billable` y `billing_basis` (`minimum`). `deliveryChange()` lleva `billable_difference` "0.0000" y `billing_difference` "0.00". | Los campos nuevos de la respuesta. |
| `e2e/support/margin.ts` | Su `FlightMargin` no lleva `billable` ni `billing_basis`. Se añadieron `reviewMonth` y `PENDING_REVIEW`. | Ese tipo declara solo lo que leen las specs, y ninguna lee aún esos campos. Si `billing.spec.ts` (tarea 16.2) los lee, se añaden entonces. |

## Tests que cambiaron de significado en los grupos 9 a 12

No los nombra la tarea, pero cambiaron por la especificación y quedaron anotados en `tasks.md`:

- **Cierre** (`test_margin_closing_service.py`):
  - Un mes con un vuelo en curso ya no cierra los terminados: se rechaza con `month_not_reviewed`. Afecta a `test_a_flight_that_has_not_ended_gets_no_row_and_its_month_is_refused`, `test_the_day_before_today_is_the_last_day_counted` y `test_a_closing_that_freezes_nothing_writes_no_header`.
  - Un mes solo con líneas committed de Adform espera ahora a que Adform cargue su último día (`…_only_waits_for_adform_to_load_its_last_day`).
  - La fila committed de `applied_rates` guarda su facturación, aquí y en `test_margin_repositories.py`.
- **Revisión** (`test_monthly_review_endpoint.py`): el test de la campaña cerrada cuenta un evento, la revisión que exigió el cierre.
- **Aceptación** (`test_acceptance_running_month_database.py`): cerrar octubre con vuelos en curso responde 409 y nombra cada campaña. Los vuelos terminados se leen como pendientes de cierre.
- **Listas de campos**: `test_margin_delivery_change_endpoint.py`, `test_billing_adjustments_endpoint.py`, `test_carryover_endpoint.py` y `test_monthly_review_endpoint.py` incluyen los campos nuevos de sus respuestas: las diferencias de facturación y el nombre del autor.
- **Frontend**:
  - «Devengado» pasa a «Facturable» o «Facturable a la fecha» en `margin-page.test.tsx`, `margin-sale.test.tsx` (con el texto de ayuda nuevo) y `target-flights.test.tsx`.
  - Los tests del cierre en `margin-closing.test.tsx` y `margin-access.test.tsx` contestan también `GET /billing`.
  - La navegación cuenta seis enlaces con «Facturación».
- **E2E**: los tres «Devengado» de `margin.spec.ts`, los flujos de cierre que revisan antes, y la navegación y la matriz de roles con «Facturación».

## Verificación

| Comprobación | Resultado |
|---|---|
| `uv run pytest tests/infrastructure/test_margin_schema.py` | 36 passed |
