"""actas_bot.py — Los originales de las actas que lee el bot.

El bot (update_fiflp.import_actas) lee cada acta de la temporada en curso, la analiza
(fiflp_acta.parse_flat_acta) y la escribe en la base. Guarda también ese dict, tal
cual, para poder rehacer lo que sale de las actas sin volver a pedirlas a la federación:

    scripts/actas_bot_<temporada>_<categoría>.jsonl     p. ej. actas_bot_2026-2027_benjamin.jsonl

Una línea por acta, JSON compacto con las claves ordenadas,
{"acta": {…}, "cod_acta": N, "leida": "<ISO UTC>"}, ordenadas por cod_acta; un acta que se vuelve a
leer sustituye a su línea. Un fichero por categoría (prebenjamín, benjamín, alevín): una temporada
entera de benjamín y prebenjamín, compacta, son ~12 MB, lejos del aviso de GitHub (50 MB).

El nombre NO es el de los raws de las tandas (actas_lotes.RAW_FILE, fiflp_actas_<S>_raw.json): con
ese nombre, import_changed_raws lo reimportaría por nombres en cada pasada en que cambiara. Lo sube
update.yml en el paso «Commit y push si hay cambios», como data-health.json (docs/federacion.md,
«Originales de las actas»).
"""
import json
import os
import tempfile
import unicodedata
from pathlib import Path

DIR = Path(__file__).resolve().parent
# Las pruebas escriben en otra carpeta (conftest); el bot, en scripts/.
ENV_DIR = "ACTAS_BOT_DIR"


def carpeta() -> Path:
    return Path(os.environ.get(ENV_DIR) or DIR)


def _categoria(categoria: str) -> str:
    """'ALEVÍN', 'Alevin' → 'alevin' (el nombre de categories.name, en minúsculas y sin tildes)."""
    return "".join(c for c in unicodedata.normalize("NFD", categoria or "")
                   if unicodedata.category(c) != "Mn").lower()


def ruta(temporada: str, categoria: str) -> Path:
    return carpeta() / f"actas_bot_{temporada}_{_categoria(categoria)}.jsonl"


def _lineas(path: Path) -> dict:
    """{cod_acta: línea} del fichero (vacío si no existe). Las líneas se conservan tal cual: reescribir
    el fichero por un acta no cambia los bytes de las demás."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    return {int(json.loads(line)["cod_acta"]): line for line in text.splitlines() if line.strip()}


def guardadas(temporada: str) -> set:
    """Los CodActa de la temporada con su original guardado, de las tres categorías."""
    out = set()
    for path in sorted(carpeta().glob(f"actas_bot_{temporada}_*.jsonl")):
        out |= set(_lineas(path))
    return out


def guardar(temporada: str, categoria: str, cod_acta: int, acta: dict, leida: str) -> None:
    """Guarda (o sustituye) el original de un acta. Atómica: el fichero nuevo se escribe en un temporal
    de la misma carpeta y sustituye al viejo con os.replace; un fallo a mitad deja el viejo entero."""
    path = ruta(temporada, categoria)
    lines = _lineas(path)
    lines[int(cod_acta)] = json.dumps({"cod_acta": int(cod_acta), "leida": leida, "acta": acta},
                                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True)
    # El temporal no acaba en .jsonl: ni guardadas ni el git add de update.yml lo ven.
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(lines[code] + "\n" for code in sorted(lines))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)               # mkstemp lo crea solo para su dueño
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def de_grupo(conn, group_id):
    """(temporada, categoría) de un grupo de la base (seasons.name, categories.name), o None."""
    row = conn.execute("""SELECT s.name, c.name FROM groups g JOIN seasons s ON s.id=g.season_id
                          JOIN categories c ON c.id=g.category_id WHERE g.id=?""", (group_id,)).fetchone()
    return tuple(row) if row and row[0] and row[1] else None
