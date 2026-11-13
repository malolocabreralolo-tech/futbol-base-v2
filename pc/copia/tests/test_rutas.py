import stat

from copia import rutas


def test_raiz_por_variable(raiz):
    assert rutas.raiz() == raiz and raiz.is_dir() and stat.S_IMODE(raiz.stat().st_mode) == 0o700


def test_raiz_por_defecto(tmp_path, monkeypatch):
    monkeypatch.delenv("FB_COPIA_RAIZ", raising=False); monkeypatch.setenv("HOME", str(tmp_path))
    assert rutas.raiz() == tmp_path / "backups" / "futbol-base"
