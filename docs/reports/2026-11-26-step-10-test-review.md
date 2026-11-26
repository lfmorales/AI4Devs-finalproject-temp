# Paso 10: revisión de los tests cuyo significado cambió con el snapshot del cierre

**Fecha:** 2026-11-26
**Change:** `closing-snapshot` (tarea 10.1)
**Commit revisado:** `2e6dafb refactor(margin): FlightEconomics ya no recibe un bruto congelado`
**Rama:** `feature/closing-snapshot`

## Qué se revisó

Los tests que la tarea 10.1 nombra porque cierran un mes o leen un vuelo cerrado, y cuyo significado cambia ahora que un vuelo cerrado se lee de su snapshot y no se recalcula con la entrega guardada. También los constructores de respuestas del frontend y los tipos de `e2e/support/margin.ts`. Las líneas son las de este commit (las del enunciado de la tarea eran las de antes de los grupos 4 y 5).

## Tests cuyo significado cambió

| Test | Qué comprueba ahora | Cambio | Grupo |
|---|---|---|---|
| `backend/tests/infrastructure/test_margin_closing_service.py:463`, cierre de un mes DOOH | el coste de plataforma (12,00 €, sobre 12.000 impresiones) y los volúmenes del vuelo antes y después del cierre; después del cierre salen del snapshot | ninguno: pasa igual, con una lectura más estricta | 5 |
| `test_margin_closing_service.py:604`, reexpresión tras el cierre | invertido: el vuelo cerrado no mueve ni el coste de plataforma (1.100,00 €) ni el aviso de bruto (sigue en `false`); lleva `delivery_changed` y su margen informativo de 3.150,00 € | reescrito | 5 |
| `test_margin_closing_service.py:395`, cifras de pendiente de cierre | además de las tasas, cada snapshot es el `snapshot_of` del vuelo tarificado y `margin_from_snapshot` sobre él da su `priced.margin` | ampliado | 4 |
| `test_margin_closing_service.py:315`, fallo a mitad | tras un fallo no queda ni fila de `applied_rates` ni tramo, ni snapshot, ni cabecera, ni lote de la cabecera; comprueba que antes del fallo se escribió algo | ampliado | 4 |
| `backend/tests/api/test_margin_coherence.py:60`, lo leído antes del cierre es lo que se congela | lo mismo, y ahora la lectura cerrada sale del snapshot | ninguno | — |
| `test_margin_coherence.py:103`, un cambio de escala o de tarifa no mueve lo cerrado | compara los vuelos enteros de la respuesta, campos del aviso incluidos | ninguno | — |
| `backend/tests/api/test_margin_contracted_revenue.py:59` y `:130` | la venta contratada, los días y los volúmenes no cambian al cerrar; los del vuelo cerrado salen del snapshot | ninguno | — |
| `backend/tests/api/test_margin_endpoint.py:81`, un vuelo cerrado se lee de lo congelado | extraprima y tasas congeladas, ya no provisional | ninguno | — |
| `backend/tests/api/test_margin_zero_sale.py:68`, la línea sin venta tras el cierre | el total del margen no cambia al cerrar; el vuelo sin venta conserva `zero_sale` desde el CPM congelado | ninguno | — |
| respuestas exactas del cierre | `test_margin_closings_endpoint.py`, `test_acceptance_closed_month_database.py` y `test_acceptance_running_month_database.py` llevan `closings` | actualizadas | 6 |
| `backend/tests/infrastructure/test_margin_schema.py:325`, ninguna columna de coma flotante | recorre también `month_closings`, `month_closing_batches` y `closed_flight_snapshots` | **ampliado en este paso** | 10 |
| `backend/tests/domain/test_flight_margin.py`, el bruto dado | los cinco tests del bruto congelado como entrada se sustituyeron por tres: `FlightEconomics` no tiene el campo, el bruto de un vuelo target es siempre el servido por el CPM y su aviso del 1 % | reescrito | 9 |

## Constructores y tipos

| Fichero | Estado |
|---|---|
| `backend/tests/fixtures/flight_inputs.py` | `flight_economics()` ya no acepta `gross_revenue` (grupo 9) |
| `frontend/tests/helpers/margin-data.ts` | `totals()` lleva `delivery_changed_count`, `flight()` lleva `delivery_changed` y `delivery_change`, y `deliveryChange()` construye la comprobación (grupo 8) |
| `frontend/tests/unit/app/margin/margin-closing.test.tsx` | **corregido en este paso:** las nueve respuestas simuladas del cierre no llevaban `closings`, que la API envía siempre. Con `closings` sin definir, `closingsMessage` compara `undefined <= 1` (falso) y la pantalla habría añadido «tiene undefined cierres»; ningún test lo buscaba. Ahora cada respuesta lleva `closings` (1 si el mes tiene algún vuelo cerrado, 0 si no) y el caso de un vuelo comprueba que no aparece ningún texto de cierres |
| `e2e/support/margin.ts` | sus interfaces declaran solo «the parts of GET /api/margin the specs read»; ningún E2E lee el aviso, por decisión de la especificación (el aviso se prueba en la API y en Vitest), así que no se añaden |

`tsc --noEmit` pasa limpio con los campos obligatorios en los tipos de `frontend/lib/api/margin.ts`.

## Verificación

| Comando | Resultado |
|---|---|
| `pytest tests/infrastructure/test_margin_schema.py` | 36 passed |
| `npx vitest run tests/unit/app/margin/margin-closing.test.tsx` | 25 passed |

## Conclusión

Dos cambios de test en este paso: la comprobación de coma flotante recorre las tres tablas nuevas, y las respuestas simuladas del cierre del frontend llevan `closings`. El resto de los tests nombrados se fue actualizando con su grupo, o pasan sin cambios y ahora comprueban, con la lectura del snapshot, lo mismo de forma más estricta.
