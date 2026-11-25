"""en_paralelo: varias tareas pesadas de una prueba, cada una en su proceso y a la vez.

Para las pruebas que trabajan sobre copias de la base real y repiten lo caro de una pasada (resolver las fichas,
~10 s; generar la web, ~50 s): la puerta de pruebas del bot (update.yml) pasa la suite entera en CADA pasada, y
así lo caro cuesta una vez en lugar de dos o tres (el runner tiene 4 núcleos). No cambia lo que se prueba: cada
tarea hace lo mismo que haría en serie, con sus propios ficheros."""
import multiprocessing
from concurrent.futures import ProcessPoolExecutor


def en_paralelo(*tareas):
    """Cada (función, argumentos) en su propio proceso, a la vez, y sus resultados en orden. Con fork: cada uno
    hereda lo que la sesión de pruebas ya ha preparado (el entorno y los monkeypatch de conftest). La función
    tiene que ser de nivel de módulo (se manda por su nombre) y devolver algo que se pueda serializar. Un fallo
    dentro de una tarea sale aquí, con su traza."""
    with ProcessPoolExecutor(max_workers=len(tareas), mp_context=multiprocessing.get_context("fork")) as pool:
        futuros = [pool.submit(funcion, *args) for funcion, args in tareas]
        return [futuro.result() for futuro in futuros]
