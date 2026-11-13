"""Útiles comunes de las pruebas: una raíz de copias temporal, bases de prueba y un remoto git local."""

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

# Esquema reducido de la base de v1: las diez tablas vigiladas y una sola clave foránea.
_ESQUEMA = """
CREATE TABLE matches (
    id         INTEGER PRIMARY KEY,
    group_id   INTEGER NOT NULL REFERENCES "groups"(id),
    jornada    TEXT,
    home_score INTEGER,
    away_score INTEGER
);
CREATE TABLE players (id INTEGER PRIMARY KEY, full_name TEXT NOT NULL);
CREATE TABLE appearances (match_id INTEGER NOT NULL, player_id INTEGER NOT NULL, role TEXT NOT NULL);
CREATE TABLE goals (id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL, minute INTEGER, player_name TEXT);
CREATE TABLE standings (id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL, team_id INTEGER NOT NULL, points INTEGER);
CREATE TABLE match_events (id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL, kind TEXT NOT NULL, minute INTEGER);
CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE "groups" (id INTEGER PRIMARY KEY, code TEXT NOT NULL, name TEXT);
CREATE TABLE scorers (id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL, player_name TEXT NOT NULL, goals INTEGER);
CREATE TABLE match_staff_all (match_id INTEGER NOT NULL, team_id INTEGER, role TEXT NOT NULL, name TEXT NOT NULL, ord INTEGER NOT NULL);

INSERT INTO players VALUES (1, 'Jugador Uno');
INSERT INTO appearances VALUES (1, 1, 'starter');
INSERT INTO goals VALUES (1, 1, 12, 'Jugador Uno');
INSERT INTO standings VALUES (1, 1, 1, 3);
INSERT INTO match_events VALUES (1, 1, 'goal', 12);
INSERT INTO teams VALUES (1, 'Equipo A');
INSERT INTO "groups" VALUES (1, 'G1', 'Grupo 1');
INSERT INTO scorers VALUES (1, 1, 'Jugador Uno', 1);
INSERT INTO match_staff_all VALUES (1, 1, 'Entrenador', 'Entrenador Uno', 1);
"""

# Una identidad de prueba y nada de la configuración del usuario: los commits de prueba no llevan su nombre ni su correo.
_GIT_PRUEBAS = {
    "GIT_AUTHOR_NAME": "Pruebas",
    "GIT_AUTHOR_EMAIL": "pruebas@example.invalid",
    "GIT_COMMITTER_NAME": "Pruebas",
    "GIT_COMMITTER_EMAIL": "pruebas@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


@pytest.fixture
def raiz(tmp_path, monkeypatch) -> Path:
    ruta = tmp_path / "copias"
    monkeypatch.setenv("FB_COPIA_RAIZ", str(ruta))
    return ruta


def crear_base(ruta: Path, partidos: int = 40, wal: bool = True) -> Path:
    con = sqlite3.connect(ruta)
    try:
        if wal:
            con.execute("PRAGMA journal_mode=WAL")
        con.executescript(_ESQUEMA)
        con.executemany(
            "INSERT INTO matches VALUES (?, 1, ?, ?, ?)",
            [(i, str(i % 10 + 1), i % 5, i % 3) for i in range(1, partidos + 1)],
        )
        con.commit()
        if wal:
            # Así la base queda entera en un solo fichero, como la que sale de git.
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()
    return ruta


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        env={**os.environ, **_GIT_PRUEBAS},
        check=True,
        capture_output=True,
        text=True,
    )
    return r.stdout.strip()


@pytest.fixture
def remoto(tmp_path) -> Path:
    repo = tmp_path / "remoto"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    crear_base(repo / "futbolbase.db")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "x_raw.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    git(repo, "add", "futbolbase.db", "scripts/x_raw.json")
    git(repo, "commit", "--quiet", "-m", "base inicial")
    return repo


def commit_base(remoto: Path, partidos: int) -> str:
    base = remoto / "futbolbase.db"
    base.unlink()
    crear_base(base, partidos=partidos)
    git(remoto, "add", "futbolbase.db")
    git(remoto, "commit", "--quiet", "-m", f"base con {partidos} partidos")
    return git(remoto, "rev-parse", "HEAD")
