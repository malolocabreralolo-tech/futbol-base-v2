"""pasada_sana.py — ¿Leyó de verdad la pasada del bot de la federación? (fase 2B de v2, objetivo O4).

Hasta noviembre de 2026 el bot podía acabar en verde sin haber leído nada (la federación sirviendo un 403
a todo, el navegador sin abrir). veredicto da los motivos por los que una pasada no es sana; update_fiflp
lo calcula al final de cada pasada y source_health lo guarda en data-health.json (runHealth). Puro: sin
base ni red. El freno (grupos sin servir) y la rotación (aplazados por plazo, los que descansan) son
funcionamiento normal: una pasada con freno que leyó bien algunos grupos es sana.
"""
import re

MAX_CODES = 12             # los códigos que nombra cada motivo; los demás, «y N más»
MAX_ERROR = 200            # el error de una pasada interrumpida, recortado


def _natural(code):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", code)]


def _codes(codes):
    names = sorted(codes, key=_natural)
    return ", ".join(names[:MAX_CODES]) + (f" y {len(names) - MAX_CODES} más" if len(names) > MAX_CODES else "")


def veredicto(estados, previstos, vacias=(), interrumpida=None):
    """Motivos por los que la pasada no es sana (lista vacía: sana).
    estados: {código de grupo: 'ok' | 'error' | 'rejected'} de los grupos que la pasada llegó a leer.
    previstos: grupos que la pasada intentó (leídos + sin servir por el freno + aplazados por plazo).
    vacias: los grupos con una jornada leída vacía que la base tiene con partidos (update_fiflp.JornadaVacia).
    interrumpida: el error con el que la pasada no llegó a acabar (sin navegador, la federación caída)."""
    reasons = []
    if interrumpida is not None:
        reasons.append(f"la federación no se pudo consultar: {str(interrumpida)[:MAX_ERROR]}")
    if vacias:
        reasons.append(f"jornada leída vacía que la base tiene con partidos: {_codes(vacias)}")
    if previstos > 0 and "ok" not in estados.values():
        reasons.append(f"la federación no sirvió ningún grupo (de {previstos} previstos)")
    else:
        failed = [code for code, status in estados.items() if status in ("error", "rejected")]
        # Más de un tercio de lo leído en error: la federación (o el lector) falla, no un grupo suelto.
        if 3 * len(failed) > len(estados):
            reasons.append(f"fallaron {len(failed)} de {len(estados)} grupos leídos: {_codes(failed)}")
    return reasons
