"""Loading of the optional YAML config file that supplies defaults for the CLI.

The file holds one section per subcommand, each mapping an option to the value
to use when the command line leaves that option out:

    run:
      ping_ip: 1.1.1.1
    display:
      format: html

Sections and options are named exactly as the command line flags are, without
the leading dashes, and anything the file does not set keeps its usual default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

import yaml

CONFIG_DIR_NAME = "checkinternet"
CONFIG_FILE_NAME = "config.yaml"


class ConfigError(Exception):
    """The config file could not be read or is not a valid configuration."""


@dataclass(frozen=True)
class Option:
    """A command option, its default, and how the config file may set it.

    from_config reads the value out of the parsed YAML document, raising
    ValueError with a description of what was expected if it is the wrong
    shape. Coercion is deliberately narrow: YAML already distinguishes numbers,
    booleans, and strings, so a mistyped value is a mistake worth reporting
    rather than something to convert.
    """

    default: Any
    from_config: Callable[[Any], Any]


# A command name mapped to the options its config file section may set.
Schema = Mapping[str, Mapping[str, Option]]

# The values a config file sets, as {command: {option: value}}.
ConfigDefaults = Dict[str, Dict[str, Any]]


def as_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise ValueError("expected a string")


def as_int(value: Any) -> int:
    # bool is a subclass of int, but `true` is never a sensible packet count.
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ValueError("expected a whole number")


def as_float(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise ValueError("expected a number")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("expected true or false")


def as_choice(choices: Sequence[str]) -> Callable[[Any], str]:
    """Reader accepting only one of choices, for options argparse restricts."""

    def from_config(value: Any) -> str:
        if isinstance(value, str) and value in choices:
            return value
        raise ValueError("expected one of: {}".format(", ".join(choices)))

    return from_config


def default_config_path() -> Path:
    """Where the config file is read from when none is named on the command line."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return config_home / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def load_config(path: Optional[str], schema: Schema) -> ConfigDefaults:
    """The defaults the config file sets, as {command: {option: value}}.

    A path names a file that has to exist. Without one the default location is
    read when it happens to hold a file, and no defaults are returned when it
    does not, so running without a config file is not an error.
    """
    config_path = _config_path(path)
    if config_path is None:
        return {}

    return _read_config(config_path, schema)


def _config_path(path: Optional[str]) -> Optional[Path]:
    """The file to read, or None when there is no config file to read."""
    if path is None:
        default_path = default_config_path()
        return default_path if default_path.is_file() else None

    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError("Config file '{}' does not exist.".format(path))
    return config_path


def _read_config(config_path: Path, schema: Schema) -> ConfigDefaults:
    try:
        with open(config_path, encoding="utf-8") as config_file:
            document = yaml.safe_load(config_file)
    except OSError as error:
        raise ConfigError(
            "Unable to read config file '{}': {}".format(config_path, error)
        ) from error
    except yaml.YAMLError as error:
        raise ConfigError(
            "Unable to parse config file '{}': {}".format(config_path, error)
        ) from error

    return _read_document(document, config_path, schema)


def _read_document(document: Any, config_path: Path, schema: Schema) -> ConfigDefaults:
    if document is None:
        return {}

    if not isinstance(document, dict):
        raise ConfigError(
            "Config file '{}' must hold a mapping of command sections, "
            "expected one of: {}.".format(config_path, _named(schema))
        )

    config: ConfigDefaults = {}
    for command, section in document.items():
        if command not in schema:
            raise ConfigError(
                "Config file '{}' has an unknown section '{}', "
                "expected one of: {}.".format(config_path, command, _named(schema))
            )
        if not isinstance(section, dict):
            raise ConfigError(
                "Config file '{}' section '{}' must hold a mapping of "
                "options to values.".format(config_path, command)
            )
        config[command] = _read_section(section, command, config_path, schema[command])

    return config


def _read_section(
    section: Mapping[Any, Any],
    command: str,
    config_path: Path,
    options: Mapping[str, Option],
) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for name, value in section.items():
        if name not in options:
            raise ConfigError(
                "Config file '{}' sets unknown option '{}' in section '{}', "
                "expected one of: {}.".format(
                    config_path, name, command, _named(options)
                )
            )
        try:
            values[name] = options[name].from_config(value)
        except ValueError as error:
            raise ConfigError(
                "Config file '{}' sets '{}' in section '{}' to '{}', {}.".format(
                    config_path, name, command, value, error
                )
            ) from error
    return values


def _named(names: Mapping[str, Any]) -> str:
    return ", ".join(sorted(names))
