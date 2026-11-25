#!/usr/bin/env python3
"""cuarentena.py — Lo que bajan las tandas del histórico no llega al bot hasta que se ha probado.

Por qué existe. El bot (update.yml) importa solo, en su pasada siguiente, cualquier raw de scripts/ que haya
cambiado (los importadores comparan la huella de su contenido: raw_imports y las huellas de grupos, goleadores
y detalle). Si una temporada bajada trae algo que rompe una prueba, o que hace crecer la base de más, la pasada
del bot sale en rojo y no publica nada, tampoco la jornada de la temporada en curso. Por eso las tandas escriben
en una carpeta aparte, scripts/historico/ (CARPETA), y solo pasa a scripts/ (promover) lo que se ha probado en
verde sobre una copia (prueba_historico.py).

Por qué una carpeta y no una lista de temporadas retenidas. Los goleadores y el detalle son un raw por
temporada para TODAS las categorías (fiflp_goleadores_<S>_raw.json, fiflp_detalle_<S>_raw.json): bajar el
alevín de 2025-26 cambia el raw que el bot ya importa para benjamín. Retener la temporada dejaría sin importar
lo de benjamín que ya estaba; una copia aparte deja el publicado intacto hasta que la nueva se prueba.

El bot no ve la carpeta porque todos sus lectores miran solo el primer nivel de scripts/ (os.listdir y glob sin
**: actas_lotes.raw_files, los import_changed_*, escudos_federacion, reconstruir; test_cuarentena lo comprueba
con todos). Un fichero que llega a scripts/ se importa en la pasada siguiente, una vez.

Los descargadores (fetch_fiflp_goleadores, _detalle, _actas) leen y escriben aquí con --carpeta: leen la copia de
la cuarentena si existe y si no la publicada (se empieza por lo que ya hay), y escriben en la cuarentena.

  python3 scripts/cuarentena.py promover --trabajos actas:2025-2026:alevin,goleadores:2025-2026 [--raiz DIR]
                                         [--lista FICHERO]
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import actas_lotes  # noqa: E402

PRINCIPAL = Path(__file__).resolve().parent          # scripts/
CARPETA = PRINCIPAL / "historico"
# Dos fases del mismo fichero: los escudos van en el raw de goleadores; el calendario, en el de detalle.
FAMILIA = {"escudos": "goleadores", "calendario": "detalle"}
CAMPOS = "fiflp_campos_raw.json"
_TEMPORADA = r"\d{4}-\d{4}"
_GOLEADORES = re.compile(rf"^fiflp_goleadores_({_TEMPORADA})_raw\.json$")
_DETALLE = re.compile(rf"^fiflp_detalle_({_TEMPORADA})_raw\.json$")
_ACTAS = re.compile(rf"^fiflp_actas_({_TEMPORADA})(?:_(" + "|".join(re.escape(l) for l in actas_lotes.LOTES if l)
                    + r"))?_(raw|index|status)\.json$")


def trabajo_de(nombre):
    """El trabajo de un fichero de la cuarentena: «goleadores:<S>», «detalle:<S>», «campos» o
    «actas:<S>:<lote>» (siempre, para el de benjamín y prebenjamín). Cualquier otro (la lista de grupos de los
    goleadores, plan.json, estado.json…), None: son del carril y no se promueven nunca."""
    nombre = os.path.basename(str(nombre))
    if nombre == CAMPOS:
        return "campos"
    for tipo, patron in (("goleadores", _GOLEADORES), ("detalle", _DETALLE)):
        m = patron.match(nombre)
        if m:
            return f"{tipo}:{m.group(1)}"
    m = _ACTAS.match(nombre)
    if m:
        return f"actas:{m.group(1)}:{m.group(2) or 'siempre'}"
    return None


def ficheros(trabajo):
    """Los nombres de los ficheros de un trabajo (una fase, los de su familia: FAMILIA). ValueError con un
    tipo, una temporada o un lote que no existen."""
    partes = str(trabajo).split(":")
    tipo = FAMILIA.get(partes[0], partes[0])
    if tipo == "campos" and len(partes) == 1:
        return [CAMPOS]
    if tipo in ("goleadores", "detalle") and len(partes) == 2 and re.fullmatch(_TEMPORADA, partes[1]):
        return [f"fiflp_{tipo}_{partes[1]}_raw.json"]
    if tipo == "actas" and len(partes) == 3 and re.fullmatch(_TEMPORADA, partes[1]):
        lote = "" if partes[2] == "siempre" else partes[2]
        if lote and lote in actas_lotes.LOTES:
            return [actas_lotes.file_name(partes[1], kind, lote) for kind in actas_lotes.KINDS]
        if partes[2] == "siempre":
            return [actas_lotes.file_name(partes[1], kind) for kind in actas_lotes.KINDS]
    raise ValueError(f"trabajo desconocido: {trabajo!r}")


def leer(nombre, carpeta, principal=PRINCIPAL):
    """De dónde se lee `nombre`: sin carpeta, el de `principal` si existe; con ella, el de la carpeta si existe
    y si no el de `principal` (se empieza por la copia de lo publicado). None si no está en ninguna."""
    for sitio in ([Path(carpeta)] if carpeta is not None else []) + [Path(principal)]:
        if (sitio / nombre).exists():
            return sitio / nombre
    return None


def escribir(nombre, carpeta, principal=PRINCIPAL):
    """Dónde se escribe `nombre`: sin carpeta, en `principal`; con ella, en la carpeta (que se crea)."""
    if carpeta is None:
        return Path(principal) / nombre
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    return Path(carpeta) / nombre


def promover(trabajos, carpeta=CARPETA, principal=PRINCIPAL):
    """Mueve (os.replace: entero o nada, cada fichero) a `principal` los ficheros de esos trabajos que estén
    en la carpeta, y da sus nombres. Con un trabajo desconocido, ValueError antes de mover nada. Lo que no es
    de ningún trabajo (la lista de grupos, el plan, el estado del carril) se queda."""
    nombres = [n for t in trabajos for n in ficheros(t)]
    movidos = []
    for nombre in dict.fromkeys(nombres):
        origen = Path(carpeta) / nombre
        if origen.exists():
            os.replace(origen, Path(principal) / nombre)
            movidos.append(nombre)
    return movidos


def en_cuarentena(carpeta=CARPETA):
    """{trabajo: [nombres]} de lo que hay en la carpeta (sin lo del carril), en orden."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return {}
    out = {}
    for path in sorted(carpeta.iterdir()):
        trabajo = trabajo_de(path.name) if path.is_file() else None
        if trabajo:
            out.setdefault(trabajo, []).append(path.name)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="La cuarentena del histórico (scripts/historico/)")
    sub = ap.add_subparsers(dest="orden", required=True)
    pro = sub.add_parser("promover", help="pasa a scripts/ los ficheros de esos trabajos")
    pro.add_argument("--trabajos", required=True, help="separados por comas: actas:2025-2026:alevin,campos…")
    pro.add_argument("--raiz", default="", help="otra raíz del proyecto (su scripts/ y scripts/historico/)")
    pro.add_argument("--lista", default="", help="dónde apuntar lo promovido: scripts/<nombre> por línea")
    args = ap.parse_args(argv)
    principal = Path(args.raiz) / "scripts" if args.raiz else PRINCIPAL
    carpeta = principal / "historico"
    trabajos = [t.strip() for t in args.trabajos.split(",") if t.strip()]
    try:
        movidos = promover(trabajos, carpeta, principal)
    except ValueError as ex:
        sys.exit(str(ex))
    if args.lista:
        Path(args.lista).write_text("".join(f"scripts/{n}\n" for n in movidos), encoding="utf-8")
    print(f"Promovidos: {', '.join(movidos) or 'ninguno'}")


if __name__ == "__main__":
    main()
