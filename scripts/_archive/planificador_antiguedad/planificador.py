"""planificador.py — El orden de una pasada del bot de la federación, por antigüedad.

Se lee primero lo que lleva más tiempo sin leerse completo (calendario, goleadores y actas), con preferencia para
los grupos del dueño. El estado es pequeño, `{código: {"completa": ISO, "intento": ISO}}`, y pasa de una pasada a
la siguiente; quien lo guarda y quien saca de la base cada `Grupo` es el bot. Puro: sin base, sin red y sin reloj
propio.

La regla:
  1. los calientes (un partido de un equipo del dueño recién jugado sin resultado o sin acta);
  2. los prioritarios abiertos cuya última lectura completa tiene más de `max_prioritario`;
  3. los demás abiertos (y los cerrados con actas por leer), por antigüedad;
  4. los cerrados sin actas pendientes, al final, por antigüedad.
La antigüedad de un grupo es la más reciente entre su última lectura completa y su último intento: si contara
solo la lectura completa, uno que falla siempre sería el primero en todas las pasadas. El que no tiene estado va
antes que todos; a igualdad, el intento más antiguo y luego el código.

Dos añadidos, apagados por defecto (los mide scripts/tests/frescura_planificador.py, docs/planificador-medidas.md):
  - `nivelar`: si en la pasada siguiente (`adelanto` después) vencerían más de `nivelar` prioritarios, los más
    viejos de ellos se adelantan a esta; sin esto, los que se leyeron juntos vencen juntos y no caben;
  - `cerrado_cada`: un cerrado sin actas pendientes cuya antigüedad pasa de esto va con los abiertos; sin esto,
    con el plazo lleno de abiertos, un cerrado no se leería nunca.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

NUNCA = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Grupo:
    codigo: str
    nivel: int            # 1 prebenjamín, 2 benjamín, 3 alevín (update_fiflp._level)
    prioritario: bool     # un equipo del dueño juega en él (update_fiflp.is_priority / pinned_groups)
    caliente: bool        # prioritario con un partido recién jugado sin resultado o sin acta (hot_reason)
    cerrado: bool         # todo jugado y la última jornada, vieja (is_closed)
    actas_pendientes: bool


def _momento(texto):
    """Un instante del estado (ISO; sin zona, UTC), o None."""
    try:
        at = datetime.fromisoformat(str(texto))
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _antiguedad(grupo, estado):
    """La clave de orden por antigüedad: los que no tienen estado, primero; después, por lo más reciente entre la
    lectura completa y el intento; a igualdad, por el intento y por el código."""
    entrada = estado.get(grupo.codigo) or {}
    completa, intento = _momento(entrada.get("completa")), _momento(entrada.get("intento"))
    ultima = max((m for m in (completa, intento) if m), default=None)
    return (ultima is not None, ultima or NUNCA, intento or NUNCA, grupo.codigo)


def delante(grupos, estado, ahora, *, max_prioritario=timedelta(hours=6), nivelar=None, adelanto=timedelta(0)):
    """Los códigos de los tramos 1 y 2 (calientes y prioritarios vencidos): los que el bot lee antes que nada."""
    def vencido(grupo, limite):
        completa = _momento((estado.get(grupo.codigo) or {}).get("completa"))
        return completa is None or ahora - completa > limite
    abiertos = [x for x in grupos if x.prioritario and not x.cerrado]
    primeros = {x.codigo for x in grupos if x.caliente} | {x.codigo for x in abiertos if vencido(x, max_prioritario)}
    if nivelar is None:
        return primeros
    proximos = sorted((x for x in abiertos if x.codigo not in primeros and vencido(x, max_prioritario - adelanto)),
                      key=lambda x: _antiguedad(x, estado))
    return primeros | {x.codigo for x in proximos[:max(0, len(proximos) - nivelar)]}


def planificar(grupos, estado, ahora, *, max_prioritario=timedelta(hours=6), nivelar=None, adelanto=timedelta(0),
               cerrado_cada=None):
    """Los códigos en el orden en que la pasada debe leerlos (la regla y los añadidos, en la docstring del
    módulo)."""
    primeros = delante(grupos, estado, ahora, max_prioritario=max_prioritario, nivelar=nivelar, adelanto=adelanto)

    def al_final(x):
        if not x.cerrado or x.actas_pendientes:
            return False
        return cerrado_cada is None or ahora - _antiguedad(x, estado)[1] <= cerrado_cada
    tramo = lambda x: 0 if x.caliente else 1 if x.codigo in primeros else 3 if al_final(x) else 2
    return [x.codigo for x in sorted(grupos, key=lambda x: (tramo(x), _antiguedad(x, estado)))]


def apuntar(estado, codigo, ahora, *, completa):
    """El estado tras leer `codigo`: `{"completa": ISO, "intento": ISO}` por grupo. Una lectura que no
    llegó a completarse solo mueve `intento`."""
    marca = ahora.isoformat(timespec="seconds")
    entrada = {**(estado.get(codigo) or {}), "intento": marca}
    if completa:
        entrada["completa"] = marca
    return {**estado, codigo: entrada}
