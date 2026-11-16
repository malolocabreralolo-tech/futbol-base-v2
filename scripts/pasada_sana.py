"""pasada_sana.py — ¿Leyó de verdad la pasada del bot de la federación?

Sin esto, el bot puede acabar en verde sin haber leído nada (la federación sirviendo un 403 a todo, el
navegador sin abrir). veredicto da los motivos por los que una pasada no es sana; update_fiflp
lo calcula al final de cada pasada y source_health lo guarda en data-health.json (runHealth). Puro: sin
base ni red. El freno (grupos sin servir) y la rotación (aplazados por plazo, los que descansan) son
funcionamiento normal: una pasada con freno que leyó bien algunos grupos es sana. Y también una pasada
SECA (ningún grupo leído bien) mientras la racha de secas no pase de LIMITE_SECA_HORAS: hay runners que
salen por una IP que la federación frena desde la primera página (se han visto 3 de 16 pasadas de un día
con 0 grupos), y la siguiente, con otra IP, lee con normalidad.
"""
import math
import re

MAX_CODES = 12             # los códigos que nombra cada motivo; los demás, «y N más»
MAX_ERROR = 200            # el error de una pasada interrumpida, recortado
LIMITE_SECA_HORAS = 6      # una racha de pasadas secas más larga, en rojo


def _natural(code):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", code)]


def _codes(codes):
    names = sorted(codes, key=_natural)
    return ", ".join(names[:MAX_CODES]) + (f" y {len(names) - MAX_CODES} más" if len(names) > MAX_CODES else "")


def seca(estados, previstos):
    """¿Una pasada seca? Había grupos previstos y ninguno acabó en «ok»."""
    return previstos > 0 and "ok" not in estados.values()


def veredicto(estados, previstos, vacias=(), interrumpida=None, horas_seca=None):
    """Motivos por los que la pasada no es sana (lista vacía: sana).
    estados: {código de grupo: 'ok' | 'error' | 'rejected'} de los grupos que la pasada llegó a leer.
    previstos: grupos que la pasada intentó (leídos + sin servir por el freno + aplazados por plazo).
    vacias: los grupos con una jornada leída vacía que la base tiene con partidos (update_fiflp.JornadaVacia).
    interrumpida: el error con el que la pasada no llegó a acabar (sin navegador, la federación caída).
    horas_seca: las horas desde la primera pasada seca de la racha en curso (0 si esta es la primera; None,
    no se sabe: como 0)."""
    reasons = []
    if interrumpida is not None:
        reasons.append(f"la federación no se pudo consultar: {str(interrumpida)[:MAX_ERROR]}")
    if vacias:
        reasons.append(f"jornada leída vacía que la base tiene con partidos: {_codes(vacias)}")
    if seca(estados, previstos):
        # Una seca suelta es una IP frenada desde la primera página: se arregla en la pasada siguiente.
        hours = horas_seca or 0
        if hours > LIMITE_SECA_HORAS:
            reasons.append(f"la federación no sirve ningún grupo desde hace {math.floor(hours)} h "
                           f"(de {previstos} previstos en esta pasada)")
    else:
        failed = [code for code, status in estados.items() if status in ("error", "rejected")]
        # Más de un tercio de lo leído en error: la federación (o el lector) falla, no un grupo suelto.
        if 3 * len(failed) > len(estados):
            reasons.append(f"fallaron {len(failed)} de {len(estados)} grupos leídos: {_codes(failed)}")
    return reasons
