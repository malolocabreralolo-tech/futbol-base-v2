"""El planificador por antigüedad (scripts/planificador.py): el orden de una pasada sale de cuándo se leyó completo
cada grupo por última vez, con preferencia para los del dueño. Rápidas: sin base, sin red y sin simulación (la
frescura que da, comparada con la de hoy, la mide scripts/tests/frescura_planificador.py)."""
from datetime import datetime, timedelta, timezone
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from planificador import Grupo, apuntar, planificar  # noqa: E402

AHORA = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def g(codigo, nivel=2, prioritario=False, caliente=False, cerrado=False, actas_pendientes=False):
    return Grupo(codigo, nivel, prioritario, caliente, cerrado, actas_pendientes)


def hace(horas):
    return (AHORA - timedelta(hours=horas)).isoformat(timespec="seconds")


def leido(horas):
    """El estado de un grupo leído completo hace `horas`."""
    return {"completa": hace(horas), "intento": hace(horas)}


def test_los_calientes_van_los_primeros():
    grupos = [g("FF1"), g("PG2", prioritario=True, caliente=True), g("AL3", prioritario=True)]
    estado = {"FF1": leido(100), "PG2": leido(1), "AL3": leido(30)}
    assert planificar(grupos, estado, AHORA)[0] == "PG2"


def test_los_prioritarios_vencidos_van_tras_los_calientes_y_los_al_dia_con_los_demas():
    grupos = [g("FF1"), g("B2", prioritario=True), g("PG2", prioritario=True, caliente=True),
              g("AL3", prioritario=True), g("FF2")]
    # B2, leído hace 7 h (más de las 6): vencido. AL3, hace 2 h: al día, va con los demás por su antigüedad.
    estado = {"FF1": leido(100), "B2": leido(7), "PG2": leido(1), "AL3": leido(2), "FF2": leido(50)}
    assert planificar(grupos, estado, AHORA) == ["PG2", "B2", "FF1", "FF2", "AL3"]
    # El plazo de los prioritarios es el que se le da.
    assert planificar(grupos, estado, AHORA, max_prioritario=timedelta(hours=1))[:3] == ["PG2", "B2", "AL3"]


def test_los_demas_abiertos_por_la_lectura_completa_mas_antigua_y_a_igualdad_por_intento_y_codigo():
    grupos = [g("FF3"), g("FF1"), g("FF2"), g("AL1"), g("AL2")]
    estado = {"FF3": leido(10), "FF1": leido(40), "FF2": leido(20),
              # AL1 y AL2, leídos completos a la vez: los dos sin intento aparte, va antes el código menor.
              "AL1": leido(30), "AL2": leido(30)}
    assert planificar(grupos, estado, AHORA) == ["FF1", "AL1", "AL2", "FF2", "FF3"]
    # A igualdad de lectura completa, el intento más antiguo primero.
    estado = {"AL1": {"completa": hace(30), "intento": hace(5)}, "AL2": {"completa": hace(30), "intento": hace(8)}}
    assert planificar([g("AL1"), g("AL2")], estado, AHORA) == ["AL2", "AL1"]


def test_los_cerrados_sin_actas_pendientes_van_al_final_por_su_antiguedad():
    grupos = [g("FF1", cerrado=True), g("FF2"), g("FF3", cerrado=True), g("FF4", cerrado=True, actas_pendientes=True)]
    estado = {"FF1": leido(300), "FF2": leido(1), "FF3": leido(500), "FF4": leido(2)}
    # FF4, cerrado con actas por leer: con los abiertos, por su antigüedad.
    assert planificar(grupos, estado, AHORA) == ["FF4", "FF2", "FF3", "FF1"]


def test_un_prioritario_cerrado_va_con_los_cerrados():
    grupos = [g("FF1"), g("FF5", prioritario=True, cerrado=True)]
    assert planificar(grupos, {"FF1": leido(1), "FF5": leido(300)}, AHORA) == ["FF1", "FF5"]


def test_un_grupo_sin_estado_va_el_primero_y_solo_una_vez():
    grupos = [g("FF1"), g("FF2"), g("D4")]
    estado = {"FF1": leido(200), "FF2": leido(100)}
    assert planificar(grupos, estado, AHORA)[0] == "D4"
    estado = apuntar(estado, "D4", AHORA, completa=True)
    assert planificar(grupos, estado, AHORA + timedelta(hours=2)) == ["FF1", "FF2", "D4"]


def test_una_lectura_incompleta_no_cuenta_como_completa():
    estado = {"B2": leido(7)}
    despues = apuntar(estado, "B2", AHORA, completa=False)
    assert despues["B2"] == {"completa": hace(7), "intento": AHORA.isoformat(timespec="seconds")}
    assert estado == {"B2": leido(7)}                    # sin tocar el de entrada
    # Un prioritario leído a medias sigue vencido: se vuelve a leer en la pasada siguiente.
    grupos = [g("FF1"), g("B2", prioritario=True)]
    assert planificar(grupos, {**despues, "FF1": leido(100)}, AHORA + timedelta(hours=2)) == ["B2", "FF1"]
    # Y completa, deja de estarlo.
    completo = apuntar(estado, "B2", AHORA, completa=True)
    assert completo["B2"] == {"completa": AHORA.isoformat(timespec="seconds"),
                              "intento": AHORA.isoformat(timespec="seconds")}
    assert planificar(grupos, {**completo, "FF1": leido(100)}, AHORA + timedelta(hours=2)) == ["FF1", "B2"]


def test_un_grupo_que_falla_siempre_no_se_queda_el_primero():
    grupos = [g("FF1"), g("FF2"), g("FF3"), g("LZ1")]
    estado = {"FF1": leido(30), "FF2": leido(20), "FF3": leido(10), "LZ1": leido(300)}
    ahora = AHORA
    primeros = []
    for _ in range(6):
        orden = planificar(grupos, estado, ahora)
        primeros.append(orden[0])
        # Cada pasada lee el primero: LZ1 falla siempre; los demás, bien.
        estado = apuntar(estado, orden[0], ahora, completa=orden[0] != "LZ1")
        ahora += timedelta(hours=2)
    assert primeros == ["LZ1", "FF1", "FF2", "FF3", "LZ1", "FF1"]
    # Y uno que nunca se ha podido leer completo tampoco.
    estado = {"FF1": leido(30), "FF2": leido(20), "LZ1": {"intento": hace(1)}}
    assert planificar(grupos[:2] + [g("LZ1")], estado, AHORA) == ["FF1", "FF2", "LZ1"]


def test_el_orden_es_determinista():
    rnd = random.Random(3)
    grupos = [g(f"FF{i}", prioritario=i % 7 == 0, caliente=i % 14 == 0, cerrado=i % 9 == 0,
                actas_pendientes=i % 18 == 0) for i in range(1, 40)]
    estado = {x.codigo: leido(rnd.choice((1, 5, 7, 30, 30, 90))) for x in grupos if rnd.random() < 0.8}
    orden = planificar(grupos, estado, AHORA)
    for _ in range(5):
        rnd.shuffle(grupos)
        assert planificar(grupos, dict(reversed(list(estado.items()))), AHORA) == orden


def test_no_pierde_ni_repite_grupos():
    rnd = random.Random(5)
    grupos = [g(f"{p}{i}", nivel=n, prioritario=rnd.random() < 0.1, caliente=rnd.random() < 0.05,
                cerrado=rnd.random() < 0.2, actas_pendientes=rnd.random() < 0.1)
              for p, n in (("PG", 1), ("FF", 2), ("AL", 3)) for i in range(1, 30)]
    estado = {x.codigo: {"completa": hace(rnd.uniform(0, 200)), "intento": hace(rnd.uniform(0, 10))}
              for x in grupos if rnd.random() < 0.7}
    orden = planificar(grupos, estado, AHORA)
    assert sorted(orden) == sorted(x.codigo for x in grupos) and len(set(orden)) == len(orden)
    assert planificar([], estado, AHORA) == []


# ── Los dos añadidos (apagados por defecto) ──────────────────────────────────

def test_nivelar_adelanta_los_prioritarios_que_vencerian_juntos_en_la_pasada_siguiente():
    al = [g(f"AL{i}", nivel=3, prioritario=True) for i in (3, 11, 20, 27)]
    grupos = [g("FF1")] + al
    # Los cuatro, leídos juntos hace 3 h: con 4,5 h de límite no vencen ahora, pero 2 h después, los cuatro a la vez.
    estado = {"FF1": leido(100), **{x.codigo: leido(3 + k / 60) for k, x in enumerate(al)}}
    limite = timedelta(hours=4.5)
    assert planificar(grupos, estado, AHORA, max_prioritario=limite)[0] == "FF1"
    orden = planificar(grupos, estado, AHORA, max_prioritario=limite, nivelar=3, adelanto=timedelta(hours=2))
    # El más viejo (AL27, por un minuto) se adelanta; quedan tres para la siguiente.
    assert orden[:2] == ["AL27", "FF1"]
    # Con tres o menos por vencer, nada se adelanta.
    assert planificar(grupos[:4], estado, AHORA, max_prioritario=limite, nivelar=3,
                      adelanto=timedelta(hours=2))[0] == "FF1"


def test_un_cerrado_que_pasa_de_cerrado_cada_va_con_los_abiertos():
    grupos = [g("FF1"), g("FF2", cerrado=True), g("FF3", cerrado=True)]
    estado = {"FF1": leido(10), "FF2": leido(30), "FF3": leido(20)}
    assert planificar(grupos, estado, AHORA) == ["FF1", "FF2", "FF3"]
    assert planificar(grupos, estado, AHORA, cerrado_cada=timedelta(days=1)) == ["FF2", "FF1", "FF3"]
