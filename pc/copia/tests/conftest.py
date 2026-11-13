"""Útiles comunes de las pruebas: una raíz de copias temporal y bases de prueba."""

import sqlite3
from pathlib import Path

import pytest

# Esquema reducido de la base de v1: las nueve tablas vigiladas y una sola clave foránea.
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

INSERT INTO players VALUES (1, 'Jugador Uno');
INSERT INTO appearances VALUES (1, 1, 'starter');
INSERT INTO goals VALUES (1, 1, 12, 'Jugador Uno');
INSERT INTO standings VALUES (1, 1, 1, 3);
INSERT INTO match_events VALUES (1, 1, 'goal', 12);
INSERT INTO teams VALUES (1, 'Equipo A');
INSERT INTO "groups" VALUES (1, 'G1', 'Grupo 1');
INSERT INTO scorers VALUES (1, 1, 'Jugador Uno', 1);
"""


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
