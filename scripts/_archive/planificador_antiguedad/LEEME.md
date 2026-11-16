# Planificador por antigüedad (fase 4B): medido, no entró

Una regla más simple para el orden de cada pasada del bot: se guarda cuándo se leyó completo cada grupo y se lee primero el que lleva más tiempo, con preferencia para los grupos del dueño.
- `planificador.py`: la regla, pura, con dos añadidos opcionales.
- `adaptador.py`: `PlanNuevo`, que la enchufa a las simulaciones con la firma de `update_fiflp.plan_groups`.
- `test_planificador.py`: sus pruebas, rápidas: `python3 -m pytest scripts/_archive/planificador_antiguedad/test_planificador.py`.

Se midió con las simulaciones de las pruebas del bot y salió **peor** que el reparto de hoy en cuatro cosas: el estado perdido, el hueco de los prioritarios en algunos casos, las actas pendientes al final de la semana y los goleadores de PG3. Por eso se quedó el planificador de hoy. Las medidas, los añadidos y el recuento de líneas están en `docs/planificador-medidas.md`, y la decisión, en `docs/decisiones.md` («El bot y la federación»).

Para volver a medirlo, desde la raíz del repositorio (unos 3 min en 8 núcleos):
- `python3 scripts/tests/frescura_planificador.py --planificador scripts/_archive/planificador_antiguedad/adaptador.py:nuevo --comparar`, con los dos añadidos;
- con `:regla` en lugar de `:nuevo`, la regla sola.

El guion carga el fichero, pone su carpeta en `sys.path` para que encuentre `planificador.py` y llama a `instalar(mp, medida)` del adaptador en cada medida. Desde código: `medir(planificar=adaptador.nuevo, semilla=7)`.
