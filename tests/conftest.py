import pytest


@pytest.fixture(autouse=True)
def wedge_dir(tmp_path, monkeypatch):
    """Cada prueba usa su propio directorio de configuración."""
    d = tmp_path / "cfg"
    monkeypatch.setenv("SERIAL_WEDGE_DIR", str(d))
    return d
