import stat

from copia import rutas


def test_raiz_por_variable(raiz):
    assert rutas.raiz() == raiz and raiz.is_dir() and stat.S_IMODE(raiz.stat().st_mode) == 0o700


def test_raiz_que_ya_existia_se_cierra(tmp_path, monkeypatch):
    # Una carpeta hecha antes, a mano o por otra herramienta, que pueden abrir otros usuarios.
    ruta = tmp_path / "copias"
    ruta.mkdir()
    for modo in (0o775, 0o755, 0o750, 0o711):
        ruta.chmod(modo)
        monkeypatch.setenv("FB_COPIA_RAIZ", str(ruta))
        assert rutas.raiz() == ruta and stat.S_IMODE(ruta.stat().st_mode) == 0o700, oct(modo)


def test_raiz_por_defecto(tmp_path, monkeypatch):
    monkeypatch.delenv("FB_COPIA_RAIZ", raising=False); monkeypatch.setenv("HOME", str(tmp_path))
    assert rutas.raiz() == tmp_path / "backups" / "futbol-base"
