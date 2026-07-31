from pathlib import Path

import pytest

from internet_troubleshooter.config import (
    ConfigError,
    Option,
    as_bool,
    as_choice,
    as_float,
    as_int,
    as_str,
    default_config_path,
    load_config,
)

SCHEMA = {
    "run": {
        "ping_ip": Option("8.8.8.8", as_str),
        "ping_count": Option(None, as_int),
        "max_packet_loss": Option(3.0, as_float),
        "skip_speedtest": Option(False, as_bool),
    },
    "display": {
        "format": Option("human", as_choice(("human", "html"))),
        "embed_plotly": Option(False, as_bool),
    },
}


def write_config(tmp_path, content, name="config.yaml"):
    config_file = tmp_path / name
    config_file.write_text(content, encoding="utf-8")
    return str(config_file)


def test_default_config_path_uses_xdg_config_home(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/somewhere/config")

    assert default_config_path() == Path("/somewhere/config/checkinternet/config.yaml")


def test_default_config_path_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", "/home/someone")

    assert default_config_path() == Path(
        "/home/someone/.config/checkinternet/config.yaml"
    )


def test_load_config_without_a_file_is_empty():
    assert load_config(None, SCHEMA) == {}


def test_load_config_reads_the_default_path():
    config_path = default_config_path()
    config_path.parent.mkdir(parents=True)
    config_path.write_text("run:\n  ping_ip: 1.1.1.1\n", encoding="utf-8")

    assert load_config(None, SCHEMA) == {"run": {"ping_ip": "1.1.1.1"}}


def test_load_config_reads_the_named_path(tmp_path):
    path = write_config(tmp_path, "run:\n  ping_ip: 1.1.1.1\n")

    assert load_config(path, SCHEMA) == {"run": {"ping_ip": "1.1.1.1"}}


def test_load_config_prefers_the_named_path_over_the_default(tmp_path):
    default = default_config_path()
    default.parent.mkdir(parents=True)
    default.write_text("run:\n  ping_ip: 9.9.9.9\n", encoding="utf-8")
    path = write_config(tmp_path, "run:\n  ping_ip: 1.1.1.1\n", name="other.yaml")

    assert load_config(path, SCHEMA) == {"run": {"ping_ip": "1.1.1.1"}}


def test_load_config_reads_every_section(tmp_path):
    path = write_config(
        tmp_path,
        "run:\n"
        "  ping_ip: 1.1.1.1\n"
        "  ping_count: 25\n"
        "  max_packet_loss: 2\n"
        "  skip_speedtest: true\n"
        "display:\n"
        "  format: html\n"
        "  embed_plotly: true\n",
    )

    assert load_config(path, SCHEMA) == {
        "run": {
            "ping_ip": "1.1.1.1",
            "ping_count": 25,
            "max_packet_loss": 2.0,
            "skip_speedtest": True,
        },
        "display": {"format": "html", "embed_plotly": True},
    }


@pytest.mark.parametrize("content", ["", "\n", "# only a comment\n", "---\n"])
def test_load_config_accepts_an_empty_file(tmp_path, content):
    assert load_config(write_config(tmp_path, content), SCHEMA) == {}


def test_load_config_accepts_an_empty_section(tmp_path):
    path = write_config(tmp_path, "run:\n  ping_ip: 1.1.1.1\ndisplay: {}\n")

    assert load_config(path, SCHEMA) == {"run": {"ping_ip": "1.1.1.1"}, "display": {}}


def test_load_config_rejects_a_missing_named_file(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        load_config(str(tmp_path / "missing.yaml"), SCHEMA)

    assert "does not exist" in str(excinfo.value)


def test_load_config_reports_an_unreadable_file(tmp_path):
    directory = tmp_path / "config_directory"
    directory.mkdir()

    with pytest.raises(ConfigError) as excinfo:
        load_config(str(directory), SCHEMA)

    assert "Unable to read config file" in str(excinfo.value)


def test_load_config_rejects_invalid_yaml(tmp_path):
    path = write_config(tmp_path, "run:\n  ping_ip: [1, 2\n")

    with pytest.raises(ConfigError) as excinfo:
        load_config(path, SCHEMA)

    assert "Unable to parse config file" in str(excinfo.value)


def test_load_config_rejects_a_document_that_is_not_a_mapping(tmp_path):
    path = write_config(tmp_path, "- run\n- display\n")

    with pytest.raises(ConfigError) as excinfo:
        load_config(path, SCHEMA)

    assert "must hold a mapping of command sections" in str(excinfo.value)


def test_load_config_rejects_an_unknown_section(tmp_path):
    path = write_config(tmp_path, "runn:\n  ping_ip: 1.1.1.1\n")

    with pytest.raises(ConfigError) as excinfo:
        load_config(path, SCHEMA)

    assert "unknown section 'runn'" in str(excinfo.value)
    assert "display, run" in str(excinfo.value)


def test_load_config_rejects_a_section_that_is_not_a_mapping(tmp_path):
    path = write_config(tmp_path, "run: 1.1.1.1\n")

    with pytest.raises(ConfigError) as excinfo:
        load_config(path, SCHEMA)

    assert "section 'run' must hold a mapping" in str(excinfo.value)


def test_load_config_rejects_an_unknown_option(tmp_path):
    path = write_config(tmp_path, "run:\n  ping_ipp: 1.1.1.1\n")

    with pytest.raises(ConfigError) as excinfo:
        load_config(path, SCHEMA)

    assert "unknown option 'ping_ipp' in section 'run'" in str(excinfo.value)
    assert "ping_ip" in str(excinfo.value)


@pytest.mark.parametrize(
    "content, expected",
    [
        ("run:\n  ping_ip: true\n", "expected a string"),
        ("run:\n  ping_count: many\n", "expected a whole number"),
        ("run:\n  ping_count: 2.5\n", "expected a whole number"),
        ("run:\n  ping_count: true\n", "expected a whole number"),
        ("run:\n  max_packet_loss: some\n", "expected a number"),
        ("run:\n  max_packet_loss: false\n", "expected a number"),
        ("run:\n  skip_speedtest: yes please\n", "expected true or false"),
        ("run:\n  skip_speedtest: 1\n", "expected true or false"),
        ("display:\n  format: pdf\n", "expected one of: human, html"),
    ],
)
def test_load_config_rejects_a_value_of_the_wrong_type(tmp_path, content, expected):
    with pytest.raises(ConfigError) as excinfo:
        load_config(write_config(tmp_path, content), SCHEMA)

    assert expected in str(excinfo.value)


def test_as_str_returns_the_value():
    assert as_str("8.8.8.8") == "8.8.8.8"


def test_as_int_returns_the_value():
    assert as_int(400) == 400


def test_as_float_widens_a_whole_number():
    value = as_float(500)

    assert value == 500.0
    assert isinstance(value, float)


@pytest.mark.parametrize("value", [True, False])
def test_as_bool_returns_the_value(value):
    assert as_bool(value) is value


def test_as_choice_returns_an_allowed_value():
    assert as_choice(("human", "html"))("html") == "html"


@pytest.mark.parametrize("value", [None, ["html"]])
def test_as_choice_rejects_anything_else(value):
    with pytest.raises(ValueError):
        as_choice(("human", "html"))(value)
