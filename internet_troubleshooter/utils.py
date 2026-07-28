import ipaddress
import logging
import re
import subprocess
import sys
from statistics import mean, variance

DEFAULT_TIMEOUT = 120

LOG_FORMAT = "%(levelname)s: %(message)s"

MAX_HOSTNAME_LENGTH = 253
HOSTNAME_LABEL_REGEX = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def is_valid_host(value):
    """True when value is an IP address or a hostname safe to pass to ping.

    Anything that could be mistaken for a command line flag is rejected.
    """
    if not isinstance(value, str) or not value:
        return False

    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass

    hostname = value[:-1] if value.endswith(".") else value
    if len(hostname) > MAX_HOSTNAME_LENGTH:
        return False

    return all(
        HOSTNAME_LABEL_REGEX.match(label) is not None for label in hostname.split(".")
    )


def configure_logging(debug=False):
    """Send log records to stderr, including DEBUG level ones when debug is set."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format=LOG_FORMAT,
        stream=sys.stderr,
    )


def run_command(command, timeout=DEFAULT_TIMEOUT):
    """Run command and return the CompletedProcess, or None if it could not run."""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(
            "ERROR: '{}' timed out after {} seconds.".format(command[0], timeout),
            file=sys.stderr,
        )
    except FileNotFoundError:
        print(
            "ERROR: '{}' command not found, is it installed and on PATH?".format(
                command[0]
            ),
            file=sys.stderr,
        )
    except OSError as error:
        print(
            "ERROR: Unable to run '{}': {}".format(command[0], error),
            file=sys.stderr,
        )
    return None


def safe_mean(values):
    """Mean of values, or None when there is no data to average."""
    if not values:
        return None
    return mean(values)


def summarize(values, title="", unit=""):
    if len(values) >= 2:
        return (
            "{0}:\n"
            "  Mean: {2:.2f}{1}\n"
            "  Variance: {3:.2f}{1}\n"
            "  Min: {4:.2f}{1}\n"
            "  Max: {5:.2f}{1}"
        ).format(title, unit, mean(values), variance(values), min(values), max(values))
    else:
        return "{0}: Not enough data.".format(title)
