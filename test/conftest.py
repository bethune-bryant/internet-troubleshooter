import pytest


@pytest.fixture(autouse=True)
def isolated_config_home(tmp_path, monkeypatch):
    """Point the default config file location at an empty directory.

    Without this, a config file in the home directory of whoever runs the
    tests would supply defaults to every CLI test in the suite.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config_home"))
