"""El adaptador del planificador por antigüedad (planificador.py, aquí al lado) a las simulaciones de
scripts/tests/frescura_planificador.py: medido en la fase 4B y no entró (docs/planificador-medidas.md; LEEME.md)."""
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import planificador as P  # noqa: E402
import source_health  # noqa: E402
import update_fiflp as U  # noqa: E402


class PlanNuevo:
    """Con la firma y la salida de update_fiflp.plan_groups, el orden de planificador.py. De la base y de
    los argumentos saca cada Grupo con las funciones de hoy (is_priority, pinned_groups, hot_reason, is_closed,
    pending_actas, _level); el estado, `{código: {"completa", "intento"}}`, lo guarda en memoria de una pasada a
    la siguiente (en el bot, la caché de GitHub Actions) y, para un grupo que no está en él, sale de `checks`
    (data-health.json), como haría el bot sin caché. Una instancia por medida: `instalar` la deja sin estado."""

    def __init__(self, **opciones):
        self.estado, self.opciones = {}, opciones

    def instalar(self, mp, medida):
        """Lo que hace falta además de plan_groups: apuntar lo leído al acabar cada pasada (en run_passes, que
        las simulaciones buscan en el módulo) y perder también este estado donde se pierde el de hoy
        (perder_estado, que _begin_sin_estado busca en `medida`, el módulo de frescura_planificador que mide)."""
        self.estado = {}
        pasada, perder, modulo = U.run_passes, medida.perder_estado, medida

        def run_passes(*a, **k):
            run = pasada(*a, **k)
            self.apuntar_pasada(run)
            return run

        def perder_los_dos():
            perder()
            self.estado = {}
        mp.setattr(U, "run_passes", run_passes)
        mp.setattr(modulo, "perder_estado", perder_los_dos)

    def apuntar_pasada(self, run):
        """Lo que la pasada leyó, a la hora de su lectura. Completo: leído bien (status ok) y sin goleadores ni
        actas por hacer (no está en extrasDeferred), lo mismo que el bot sabe de sí; lo que leyó con error, solo
        un intento; lo que el freno o el plazo no dejaron empezar (unserved, deferred), nada."""
        report = source_health._report or {}
        cortados = set((report.get("run") or {}).get("extrasDeferred") or [])
        for code, status in run["estados"].items():
            at = U.checked_at(report["groups"][code])
            self.estado = P.apuntar(self.estado, code, at, completa=status == "ok" and code not in cortados)

    @staticmethod
    def respaldo(checks):
        """El estado que da data-health.json: su última comprobación correcta como lectura completa; una que
        falló, como intento."""
        out = {}
        for code, check in (checks or {}).items():
            at = U.checked_at(check)
            if at is not None:
                iso = at.isoformat(timespec="seconds")
                out[code] = {"completa": iso, "intento": iso} if U.checked_ok(check) else {"intento": iso}
        return out

    def __call__(self, conn, groups, checks, today, number, priority=None, pinned=None, env=None, now=None):
        if not groups:
            return U.Plan([], [], set(), number, [], {}, set())
        now = U._aware(now or datetime.now(timezone.utc))
        keys = U.priority_keys(U.priority_teams() if priority is None else priority)
        pinned = U.pinned_groups() if pinned is None else set(pinned)
        ids = [g[0] for g in groups]
        marks = ",".join("?" * len(ids))
        categories = dict(conn.execute(
            f"SELECT g.id, c.name FROM groups g JOIN categories c ON c.id=g.category_id WHERE g.id IN ({marks})", ids))
        teams = {}
        for gid, name in conn.execute(
                f"""SELECT s.group_id, t.name FROM standings s JOIN teams t ON t.id=s.team_id WHERE s.group_id IN ({marks})
                    UNION SELECT m.group_id, t.name FROM matches m JOIN teams t ON t.id IN (m.home_team_id, m.away_team_id)
                    WHERE m.group_id IN ({marks})""", ids + ids):
            teams.setdefault(gid, []).append(name)
        grupos, hot = [], {}
        for gid, code, _ in groups:
            closed = U.is_closed(conn, gid, today)
            mine = code in pinned or any(U.is_priority(t, keys) for t in teams.get(gid, []))
            why = U.hot_reason(conn, gid, keys, now, checks.get(code)) if mine and not closed else None
            if why:
                hot[code] = why
            grupos.append(P.Grupo(code, U._level(categories.get(gid), code), mine, bool(why), closed,
                                  bool(U.pending_actas(conn, gid))))
        estado = {**self.respaldo(checks), **self.estado}
        # Lo que mira stale: un prioritario toca si en la pasada siguiente (PASS_EVERY después) pasaría de su
        # frescura (FIFLP_PRIORITY_MAX_H) con PASS_SLACK de margen; el planificador lo mira ahora.
        limite = U.priority_max_age(env) - U.PASS_EVERY + U.PASS_SLACK
        opciones = {"adelanto": U.PASS_EVERY, **self.opciones}
        orden = P.planificar(grupos, estado, now, max_prioritario=limite, **opciones)
        primeros = P.delante(grupos, estado, now, max_prioritario=limite,
                             **{k: v for k, v in opciones.items() if k in ("nivelar", "adelanto")})
        rows = {g[1]: g for g in groups}
        fresh = [rows[x.codigo] for x in grupos if x.prioritario and not x.cerrado and x.codigo not in primeros]
        return U.Plan([rows[c] for c in orden], fresh, primeros, number, fresh, hot, set(primeros))


# La regla sola y con sus dos añadidos (por qué, en docs/planificador-medidas.md): lo que se pasa a
# `frescura_planificador.py --planificador <este fichero>:regla` o `:nuevo`.
AÑADIDOS = {"nivelar": 3, "cerrado_cada": timedelta(days=1)}
regla = PlanNuevo()
nuevo = PlanNuevo(**AÑADIDOS)
