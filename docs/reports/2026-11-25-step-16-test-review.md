# Paso 16: revisión de los tests que construyen líneas, entregas, vuelos, respuestas de margen o peticiones de registro

**Fecha:** 2026-11-25
**Change:** `equativ-deals` (tarea 16.1)
**Commit revisado:** `05aa41f test(e2e): demo de Deal con el ejemplo resuelto y sus E2E`
**Rama:** `feature/equativ-deals`

## Qué se revisó

Todo test, ayudante de test y script que construye una línea, una fila de entrega, un vuelo, una respuesta de estado o de margen o una petición de registro, para comprobar que lleva los campos nuevos de este change: `volume_commitment` en la línea; `buyer_spend`, `reported_revenue`, `third_party_data_cost` y `audience_data_cost` en la entrega; `volume_commitment`, `reported_revenue`, `buyer_spend`, `data_cost` y `gross_revenue` en las entradas del margen; y `volume_commitment`, `gross_revenue` y los dos avisos en las respuestas. Además, que ningún test llama a la API real de Equativ.

### Backend

| Constructor o ayudante | Dónde | Estado |
|---|---|---|
| `dsp_row()` | `backend/tests/fixtures/delivery_rows.py` | acepta y pasa los cuatro importes (por defecto 0) |
| `DailyDelivery(...)` | `delivery_rows.py` y `backend/tests/domain/test_flight_delivery.py` | los dos pasan los cuatro importes; el segundo los suma en `deliveries_in_window` (tarea 7.5) |
| `insert_delivery(...)` | `backend/tests/fixtures/delivery_data.py` | acepta los cuatro importes |
| `insert_campaign_line(...)` | `delivery_data.py` | inserta el registro directamente: la línea toma `committed` del valor por defecto de la base; los tests que necesitan una línea `target` la actualizan explícitamente |
| `DailyDeliveryRecord(**fields)` | `backend/tests/infrastructure/test_delivery_models.py` | recibe las columnas nuevas, cubiertas por los tests de la migración de importes |
| `flight_economics()` y `flight_facts()` | `backend/tests/fixtures/flight_inputs.py` | llevan `volume_commitment`, los tres importes comunicados y, en `flight_economics`, `gross_revenue`; los valores por defecto (`committed`, ceros, `None`) viven aquí, no en el dominio |
| `FlightDeliveryFigures(...)` | `backend/tests/application/test_campaign_status_service.py` | el ayudante `_figures()` lleva `volume_commitment` (por defecto `committed`) |
| canales y DSP sembrados | `backend/tests/fixtures/master_data.py` | `Deal` y `Equativ` existen; los tests de API los encuentran sin crearlos |
| semillas | `backend/scripts/seed_margin_demo.py` | la demo `DEMO-MARGEN-DEAL` registra su línea con `volume_commitment` `target` y el resto con `committed` |

`FlightEconomics(` y `FlightFacts(` solo se construyen en `flight_inputs.py` dentro de los tests; `FrozenRates(` no se construye en ningún test (solo en el repositorio).

### Frontend y E2E

| Fichero | Estado |
|---|---|
| `frontend/tests/helpers/margin-data.ts` (`totals()`, `flight()`) | llevan `volume_commitment`, `gross_revenue`, los dos avisos y los dos recuentos |
| `frontend/tests/unit/app/status/status-page.test.tsx` (`row()`) | lleva `volume_commitment` |
| `frontend/tests/unit/app/status/status-states.test.tsx` | el objeto literal lleva `volume_commitment` |
| `frontend/tests/unit/lib/api/status-and-exceptions.test.ts` (`STATUS_ROW`) | lleva `volume_commitment` |
| `e2e/support/margin.ts`, `e2e/support/campaign-form.ts` y `e2e/tests/status.spec.ts` | las interfaces de las respuestas incluyen `volume_commitment` y, en el margen, `gross_revenue` |

`tsc --noEmit` pasa limpio con los campos obligatorios en los tipos de `frontend/lib/api`, de modo que ningún objeto tipado de las respuestas queda sin ellos.

## Cada ruta de registro envía `volume_commitment`

```
git grep -n "volume_commitment" -- backend/tests frontend/tests e2e
```

| Carpeta | Líneas | Ficheros |
|---|---:|---:|
| `backend/tests` | 133 | 28 |
| `frontend/tests` | 16 | 11 |
| `e2e` | 13 | 7 |

De los ficheros que montan una línea de campaña (los que nombran `market_description`), los que envían una petición de registro llevan todos el compromiso: los tests de API y del servicio de registro, el esquema y el formulario del frontend con sus tests, `e2e/support/campaigns.ts` (con su comprobación en `campaigns.test.mjs`) y la demo de margen. Los seis que no lo nombran no envían una petición: insertan filas directamente en la base (`delivery_data.py`, `test_campaign_line_flight_models.py` y cuatro tests de migración que escriben SQL en revisiones anteriores o posteriores a la columna, donde la base pone `committed` por defecto).

## Ningún test llama a la API real de Equativ

- **La guarda.** `backend/tests/conftest.py` define `no_real_equativ_requests`, un fixture `autouse` que envuelve los transportes reales de `httpx` (síncrono y asíncrono) y falla en el acto, nombrando el host, ante cualquier petición a `eqtv.io`, `smartadserverapis.com` o un subdominio suyo, antes de abrir una conexión. `httpx.MockTransport` no se envuelve, así que el Equativ falso de los tests sigue respondiendo.
- **Está activa en toda la suite.** Se define una sola vez y ningún otro `conftest.py` la redefine. `pytest --setup-plan` (que lista los fixtures de cada test sin ejecutarlo) la monta en **2.697 de 2.697** tests.
- **Se prueba a sí misma.** `backend/tests/test_no_real_equativ_calls.py` comprueba que una petición real, síncrona o asíncrona, a los dos hosts y a un subdominio falla con `RealEquativRequestBlocked`; que un `MockTransport` a las mismas URL se sirve; y que otro host no se bloquea. Las peticiones reales de esas pruebas pasan por un proxy en un puerto local cerrado, de modo que, si la guarda faltara, fallarían en la máquina sin llegar a Equativ.
- **Cada cliente de Equativ de los tests usa el falso.** Los seis ficheros que construyen `EquativDeliveryClient` le pasan el cliente de `tests/fixtures/fake_equativ.py` (un `MockTransport`). El test de `run_ingestion` que arranca con credenciales y sin cliente inyectado comprueba que la ejecución termina con código 1 y `RealEquativRequestBlocked`: la guarda la corta.
- **Fuera del backend.** Ningún test de frontend ni E2E nombra un host de Equativ (`git grep -i "eqtv\.io\|smartadserverapis" -- e2e frontend/tests` no encuentra nada). La demo de Deal de los E2E escribe sus entregas directamente en la base, bajo un lote de Equativ sembrado.

## Tests cuyo significado cambió

| Test | Cambio | Grupo |
|---|---|---|
| `backend/tests/domain/test_margin_model_integrity.py:69` | de «un Deal y un Directo con las mismas cifras tienen el mismo margen» a «con el mismo compromiso y las mismas cifras», parametrizado con `committed` y `target` | 7 |
| `backend/tests/domain/test_pacing.py`, casos de sobreentrega | no cambian: `calculate_pacing` sigue dando `over_delivering` e `is_deviating` sin mirar el compromiso; el aviso por compromiso (`pacing_flag`) se prueba en casos nuevos | 12 |
| escenario «Every platform type uses the same model» de `finance/margin-calculation` | la delta lo reescribe con «the same commitment and the same figures»; lo cubre el test de `:69` | 7 |
| `backend/tests/application/test_dsp_mapping_service.py`, DSP sin conector | el ejemplo pasa de Equativ a Displayce | 5 |
| `backend/tests/api/test_campaign_status_endpoint.py`, recorrido de trading | se amplía con una línea `target` con importes y las palabras `gross`, `buyer`, `reported` y `data_cost` | 13 |
| `backend/tests/api/test_seed_margin_demo_states.py` | el conjunto de campañas incluye `DEMO-MARGEN-DEAL` y cerrar el mes anterior cierra 2 flights | 15 |
| `e2e/tests/margin.spec.ts`, venta del mes anterior | la etiqueta se elige por compromiso («Venta objetivo» para la demo de Deal) | 15 |
| `e2e/tests/status.spec.ts`, filas del DEMO Channel | se limita a las líneas `committed`, que es lo que describe su título | 15 |

## Conclusión

No hizo falta cambiar ningún test en esta tarea: los constructores se fueron actualizando con cada grupo (1 a 15) y el compilador de tipos, mypy y las suites lo confirman. Queda una observación, sin acción: `insert_campaign_line` no tiene parámetro `volume_commitment`; los tests que necesitan una línea `target` la actualizan con un `UPDATE` explícito, y el resto depende del valor por defecto de la base, que es el mismo que el de producción.
