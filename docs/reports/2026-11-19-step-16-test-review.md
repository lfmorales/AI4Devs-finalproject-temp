# Paso 16: revisión de los tests que construyen entregas, vuelos o respuestas de margen

**Fecha:** 2026-11-19
**Change:** `ctv-and-delivery-metric` (tarea 16.1)
**Commit revisado:** `b3fba63 test(e2e): campaña DOOH de demostración y unidad de entrega en estado y margen`
**Rama:** `feature/ctv-and-delivery-metric`

## Qué se revisó

Todo test, ayudante de test y script que construye una fila de entrega, un vuelo o una respuesta de estado o de margen, para comprobar que lleva los campos nuevos (`ots`, `video_completions`, `delivered`, `delivery_metric`) y que ningún test llama `OOH` o `Digital` a un canal.

### Backend

| Constructor o ayudante | Dónde | Estado |
|---|---|---|
| `dsp_row()` y `daily_delivery()` | `backend/tests/fixtures/delivery_rows.py` | llevan `ots` y `video_completions` (commits `3433d9a`, `8c18079`) |
| `DailyDelivery(...)` | `delivery_rows.py` y `backend/tests/domain/test_flight_delivery.py` | los dos pasan `ots` y `video_completions` |
| `DspDeliveryRow(...)` | `delivery_rows.py` (único) | pasa `ots` y `video_completions` |
| `insert_campaign_line(..., delivery_metric=)` e `insert_delivery(..., ots=)` | `backend/tests/fixtures/delivery_data.py` | aceptan la métrica del canal y los OTS de la fila (commits `ba5f50b`, `e1bd7ea`) |
| `DailyDeliveryRecord(...)` | `delivery_data.py` y `backend/tests/infrastructure/test_delivery_models.py` | el primero pasa `ots`; el segundo recibe `**fields` con la columna nueva, probada en `test_delivery_models.py` |
| `flight_economics()` y `flight_facts()` | `backend/tests/fixtures/flight_inputs.py` (nuevo) | los 14 sitios de test que construían `FlightEconomics` y `FlightFacts` pasan por aquí; `delivered` y `delivery_metric` son obligatorios en el dominio (commit `15d0ab7`) |
| `InMemoryMasterRepository(ots_channel_ids=)` | `backend/tests/fixtures/in_memory_campaign_registration.py` | devuelve un `Channel` con `delivery_metric` (commit `e1bd7ea`) |
| canales sembrados | `backend/tests/fixtures/master_data.py` | `Directo`, `Deal`, `DOOH` (ots) y `CTV` (commit `e1bd7ea`) |
| semillas | `backend/scripts/seed_dev_data.py`, `seed_margin_demo.py` | cuatro canales con su métrica; la demo de margen añade `DEMO-MARGEN-DOOH` en OTS |

Hay un solo `FlightEconomics(` que no pasa por el ayudante: el del propio ayudante.

### Frontend y E2E

| Fichero | Estado |
|---|---|
| `frontend/tests/helpers/margin-data.ts` (`totals()`, `flight()`) | llevan `delivery_metric` y `delivered`; si una prueba da solo `delivered_impressions`, `delivered` se deriva de él (commit `4ce4252`) |
| `frontend/tests/unit/app/status/status-page.test.tsx` (`row()`) | lleva `delivery_metric`, `delivered` y `delivered_impressions` |
| `frontend/tests/unit/app/status/status-states.test.tsx` | el objeto literal lleva los tres |
| `frontend/tests/unit/lib/api/status-and-exceptions.test.ts` (`STATUS_ROW`) | lleva los tres |
| `e2e/support/margin.ts` y `e2e/tests/status.spec.ts` | las interfaces de la respuesta incluyen `delivery_metric` y `delivered` |

`tsc --noEmit` pasa limpio con los campos obligatorios, de modo que ningún objeto tipado de las respuestas queda sin ellos.

## Búsqueda de `OOH` y `Digital`

```
git grep -nwE "OOH|Digital" -- backend/tests backend/scripts frontend/tests e2e deploy
```

Una sola coincidencia:

```
backend/tests/scripts/test_seed_dev_data.py:147:    assert not names & {"OOH", "Digital"}
```

Es una aserción negativa: comprueba que la semilla de desarrollo ya no deja esos dos canales. Ningún test los usa como canal. Fuera de esas carpetas solo aparecen en prosa de documentación (`OOH/DOOH` como nombre del negocio) y no son nombres de canal.

## Conclusión

No hizo falta cambiar ningún test en esta tarea: los constructores se habían ido actualizando con cada grupo (3 a 15) y el compilador de tipos y la suite lo confirman. Quedan dos observaciones, sin acción:

- `insert_delivery` no tiene parámetro `video_completions`: ningún cálculo de estado ni de margen lo lee, así que la columna toma su valor por defecto (0) en esos tests. Los de ingestión lo cubren por su cuenta (`test_delivery_models.py` y los tests de `DspDeliveryRow`).
- Los 14 sitios que pasan por `flight_economics()` y `flight_facts()` tienen como valor por defecto «impresiones» y `delivered = delivered_impressions`; el código de producción nunca depende de ese valor.
