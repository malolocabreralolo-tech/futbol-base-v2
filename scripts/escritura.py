"""Escritura atómica de los ficheros del bot: originales de la federación, estado y lo que se publica.

Un corte a mitad (el plazo del paso, un fallo del runner) no puede dejar un fichero truncado: se escribe en un
temporal de la misma carpeta y se cambia por el de verdad de golpe (os.replace)."""
import os
import stat
import tempfile


def escribir_atomico(path, contenido, *, encoding="utf-8") -> None:
    """`contenido` (str o bytes) acaba en `path` entero o no acaba: temporal en la misma carpeta,
    fsync, os.replace. Si algo falla, el fichero de antes queda intacto y el temporal se borra."""
    path = os.fspath(path)
    carpeta, nombre = os.path.split(os.path.abspath(path))
    try:
        permisos = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        permisos = 0o644
    fd, tmp = tempfile.mkstemp(dir=carpeta, prefix=nombre + ".", suffix=".tmp")
    try:
        # El texto, con la misma traducción de saltos de línea que open(path, "w"): el fichero no cambia un byte.
        try:
            if isinstance(contenido, str):
                f = os.fdopen(fd, "w", encoding=encoding)
            else:
                f = os.fdopen(fd, "wb")
        except BaseException:
            os.close(fd)
            raise
        with f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, permisos)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    _sincroniza_carpeta(carpeta)


def _sincroniza_carpeta(carpeta):
    """El cambio de nombre, también en disco; donde no se puede abrir una carpeta (Windows), se deja."""
    try:
        fd = os.open(carpeta, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
