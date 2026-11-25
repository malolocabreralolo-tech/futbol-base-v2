#!/usr/bin/env python3
"""prueba_historico.py — Lo bajado del histórico se prueba sobre una copia antes de pasar al bot.

Por qué. Lo que pasa de scripts/historico/ a scripts/ (cuarentena.promover) lo importa el bot en su pasada
siguiente, y una pasada que sale en rojo no publica nada, tampoco la jornada de la temporada en curso. Así que
antes de promover se hace sobre una copia del repositorio lo mismo que hará el bot con esos raws
(fetch_futbolaspalmas.py --solo-historico: importar las temporadas pasadas, las fichas y los data-*.js, sin
leer ninguna fuente), se pasan sobre esa copia la base sana y todas las suites, y el veredicto es todo o nada:
verde solo si la importación acabó bien, las pruebas salieron bien, la base no llega a MB_MAX y la importación
cabe en una pasada del bot (IMPORTACION_MAX_S).

  python3 scripts/prueba_historico.py importar --raiz DIR --medida FICHERO
      ejecuta DIR/scripts/fetch_futbolaspalmas.py --solo-historico con cwd=DIR, mide los segundos y el tamaño
      de DIR/futbolbase.db (más su -wal) antes y después, escribe {"mb_antes", "mb_despues", "segundos",
      "codigo"} y sale con el código de la importación;
  python3 scripts/prueba_historico.py veredicto --medida FICHERO --pruebas success|failure --salida FICHERO
      escribe el veredicto, pone verde=true|false en $GITHUB_OUTPUT y sale con 0 (el rojo lo dice el
      veredicto, no el código: el carril apunta el motivo y sigue).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_sana  # noqa: E402
from escritura import escribir_atomico  # noqa: E402
from source_health import MB  # noqa: E402

# El job del bot dura 40 min y una pasada, ~20-26: una importación de más de 10 min no cabe en la primera
# pasada que la haga (y esa pasada no publicaría nada).
IMPORTACION_MAX_S = 600
# Desde AVISO_MB (80) la web avisa del tamaño y hace falta la parte D (la base en sombra); el bot deja de subir
# la base a PARADA_MB (95). Lo del histórico no puede llevarla hasta ahí.
MB_MAX = base_sana.AVISO_MB


def veredicto(mb_antes, mb_despues, segundos, pruebas):
    """{"verde", "motivo", "mb_antes", "mb_despues", "segundos"}: verde sin motivo, o rojo con el primero que
    se cumpla (las pruebas; el tamaño, desde MB_MAX; el tiempo, más de IMPORTACION_MAX_S)."""
    if not pruebas:
        motivo = "las pruebas fallaron"
    elif mb_despues >= MB_MAX:
        motivo = f"la base pasaría a {mb_despues:.1f} MB (desde {MB_MAX} hace falta la parte D)"
    elif segundos > IMPORTACION_MAX_S:
        motivo = (f"la importación tarda {segundos / 60:.0f} min (más de {IMPORTACION_MAX_S / 60:.0f}: no cabe en "
                  "una pasada del bot)")
    else:
        motivo = ""
    return {"verde": not motivo, "motivo": motivo, "mb_antes": mb_antes, "mb_despues": mb_despues,
            "segundos": segundos}


def _mb(db):
    """Los MB de la base `db` con su -wal (va en modo WAL: lo escrito puede estar aún en él); 0 sin base."""
    total = sum(p.stat().st_size for p in (Path(db), Path(f"{db}-wal")) if p.exists())
    return round(total / MB, 3)


def importar(raiz, medida):
    """La importación del histórico sobre la copia de `raiz`, medida; da su código de salida."""
    raiz = Path(raiz).resolve()
    db = raiz / "futbolbase.db"
    antes = _mb(db)
    t0 = time.monotonic()
    codigo = subprocess.run([sys.executable, str(raiz / "scripts" / "fetch_futbolaspalmas.py"), "--solo-historico"],
                            cwd=raiz).returncode
    segundos = round(time.monotonic() - t0, 1)
    datos = {"mb_antes": antes, "mb_despues": _mb(db), "segundos": segundos, "codigo": codigo}
    escribir_atomico(Path(medida), json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f"Importación del histórico: código {codigo}, {segundos:.0f} s, la base de {antes:.1f} a "
          f"{datos['mb_despues']:.1f} MB")
    return codigo


def veredicto_de(medida, pruebas):
    """El veredicto de la orden `veredicto`: rojo si no hay medida o si la importación no acabó bien (código
    distinto de 0: un importador falló, aunque las pruebas salieran bien); si no, veredicto()."""
    try:
        m = json.loads(Path(medida).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"verde": False, "motivo": "no hay medida de la importación", "mb_antes": None, "mb_despues": None,
                "segundos": None}
    if m.get("codigo") != 0:
        return {"verde": False, "motivo": f"la importación falló (código {m.get('codigo')})",
                "mb_antes": m.get("mb_antes"), "mb_despues": m.get("mb_despues"), "segundos": m.get("segundos")}
    return veredicto(m["mb_antes"], m["mb_despues"], m["segundos"], pruebas == "success")


def main(argv=None):
    ap = argparse.ArgumentParser(description="La prueba del histórico sobre una copia")
    sub = ap.add_subparsers(dest="orden", required=True)
    imp = sub.add_parser("importar", help="importa el histórico en la copia y lo mide")
    imp.add_argument("--raiz", required=True, help="la raíz de la copia (su scripts/ y su futbolbase.db)")
    imp.add_argument("--medida", required=True, help="dónde escribir la medida (JSON)")
    ver = sub.add_parser("veredicto", help="el veredicto de la prueba")
    ver.add_argument("--medida", required=True)
    ver.add_argument("--pruebas", default="", help="success si la base sana y las suites salieron bien")
    ver.add_argument("--salida", required=True, help="dónde escribir el veredicto (JSON)")
    args = ap.parse_args(argv)
    if args.orden == "importar":
        return importar(args.raiz, args.medida)
    v = veredicto_de(args.medida, args.pruebas)
    escribir_atomico(Path(args.salida), json.dumps(v, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"verde={'true' if v['verde'] else 'false'}\n")
    print("Veredicto: " + ("verde" if v["verde"] else f"rojo, {v['motivo']}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
