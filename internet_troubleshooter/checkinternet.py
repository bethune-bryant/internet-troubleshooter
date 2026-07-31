#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
from datetime import datetime
import sys
from typing import Dict, List, Optional, Tuple

from internet_troubleshooter import __version__
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
from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult, default_hop_ping_count
from internet_troubleshooter.speed_test import SpeedResult
from internet_troubleshooter.render import (
    PLOT_DOWNLOAD_MBPS,
    PLOT_LATENCY_MS,
    PLOT_PACKET_LOSS_PCT,
    PLOT_UPLOAD_MBPS,
    RenderThresholds,
    to_html,
    to_human,
)
from internet_troubleshooter.result import TestResult
from internet_troubleshooter.utils import configure_logging, is_valid_host

logger = logging.getLogger(__name__)

STDIN_YAML_FILE = "-"

DISPLAY_FORMATS = ("human", "html")

# The options of each subcommand that the config file may supply a default for,
# along with the default used when neither the command line nor the config file
# sets them. argparse suppresses these defaults so that a parsed namespace holds
# only what was actually passed, which is what lets the config file fill in the
# rest without overriding an explicit flag.
RUN_OPTIONS: Dict[str, Option] = {
    "ping_ip": Option("8.8.8.8", as_str),
    "ping_count": Option(None, as_int),
    "trace_hop_ping_count": Option(None, as_int),
    "max_packet_loss": Option(3.0, as_float),
    "skip_speedtest": Option(False, as_bool),
    "skip_pingtest": Option(False, as_bool),
    "yaml_file": Option(None, as_str),
}

DISPLAY_OPTIONS: Dict[str, Option] = {
    "yaml_file": Option(None, as_str),
    "format": Option("human", as_choice(DISPLAY_FORMATS)),
    "html_file": Option(None, as_str),
    "embed_plotly": Option(False, as_bool),
    "target_download_mbps": Option(PLOT_DOWNLOAD_MBPS, as_float),
    "target_upload_mbps": Option(PLOT_UPLOAD_MBPS, as_float),
    "target_latency_ms": Option(PLOT_LATENCY_MS, as_float),
    "target_packet_loss_pct": Option(PLOT_PACKET_LOSS_PCT, as_float),
}

COMMAND_OPTIONS: Dict[str, Dict[str, Option]] = {
    "run": RUN_OPTIONS,
    "display": DISPLAY_OPTIONS,
}


def _default_note(options: Dict[str, Option], name: str) -> str:
    return "(default: {})".format(options[name].default)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test internet connection.")
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s {}".format(__version__),
        help="Print the version and exit.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print progress and raw command output to stderr.",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Config file of defaults to read instead of {}. Values in it are "
        "used for the options that are not passed on the command line.".format(
            default_config_path()
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_cmd = subparsers.add_parser("run", help="Run the tests once.")

    run_cmd.add_argument(
        "--ping_ip",
        default=argparse.SUPPRESS,
        help="IP address or hostname to ping. {}".format(
            _default_note(RUN_OPTIONS, "ping_ip")
        ),
    )
    run_cmd.add_argument(
        "--ping_count",
        default=argparse.SUPPRESS,
        type=int,
        help="Packets to send. (default: 400 as root, otherwise 10)",
    )
    run_cmd.add_argument(
        "--trace_hop_ping_count",
        default=argparse.SUPPRESS,
        type=int,
        help="Packets to send to each traceroute hop. "
        "(default: 50 as root, otherwise 10)",
    )
    run_cmd.add_argument(
        "--max_packet_loss",
        default=argparse.SUPPRESS,
        type=float,
        help="Packet loss percent above which a traceroute is run. {}".format(
            _default_note(RUN_OPTIONS, "max_packet_loss")
        ),
    )
    run_cmd.add_argument(
        "--skip_speedtest",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Do not run the speed test.",
    )
    run_cmd.add_argument(
        "--skip_pingtest",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Do not run the ping test, and therefore never traceroute.",
    )
    run_cmd.add_argument(
        "--yaml_file",
        default=argparse.SUPPRESS,
        type=str,
        help="File to append this run's results to, for later display.",
    )

    run_cmd.set_defaults(func=run)

    display_cmd = subparsers.add_parser(
        "display", help="Summarize results logged by previous runs."
    )

    display_cmd.add_argument(
        "--yaml_file",
        default=argparse.SUPPRESS,
        help="File of logged results to read, or '{}' to read them from stdin. "
        "Required unless the config file sets it.".format(STDIN_YAML_FILE),
    )
    display_cmd.add_argument(
        "--format",
        default=argparse.SUPPRESS,
        choices=DISPLAY_FORMATS,
        help="Output format, written to stdout unless --html_file names a "
        "file to write the HTML report to. {}".format(
            _default_note(DISPLAY_OPTIONS, "format")
        ),
    )
    display_cmd.add_argument(
        "--html_file",
        default=argparse.SUPPRESS,
        type=str,
        help="File to write the HTML report to instead of stdout. Only used "
        "with '--format html'.",
    )
    display_cmd.add_argument(
        "--embed_plotly",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Inline plotly.js in the HTML report so it opens offline, "
        "instead of loading it from the plotly CDN.",
    )
    display_cmd.add_argument(
        "--target_download_mbps",
        default=argparse.SUPPRESS,
        type=float,
        help="Download speed the HTML report treats as healthy. {}".format(
            _default_note(DISPLAY_OPTIONS, "target_download_mbps")
        ),
    )
    display_cmd.add_argument(
        "--target_upload_mbps",
        default=argparse.SUPPRESS,
        type=float,
        help="Upload speed the HTML report treats as healthy. {}".format(
            _default_note(DISPLAY_OPTIONS, "target_upload_mbps")
        ),
    )
    display_cmd.add_argument(
        "--target_latency_ms",
        default=argparse.SUPPRESS,
        type=float,
        help="Highest latency the HTML report treats as healthy. {}".format(
            _default_note(DISPLAY_OPTIONS, "target_latency_ms")
        ),
    )
    display_cmd.add_argument(
        "--target_packet_loss_pct",
        default=argparse.SUPPRESS,
        type=float,
        help="Highest packet loss the HTML report treats as healthy. {}".format(
            _default_note(DISPLAY_OPTIONS, "target_packet_loss_pct")
        ),
    )

    display_cmd.set_defaults(func=display)

    return parser


def _apply_config_defaults(args: argparse.Namespace) -> None:
    """Fill in the options the command line left out from the config file.

    Only options missing from the namespace are set, so an explicit flag always
    wins over the config file, which in turn wins over the built in default.
    """
    try:
        config = load_config(args.config, COMMAND_OPTIONS)
    except ConfigError as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        raise SystemExit(2)

    from_config = config.get(args.command, {})
    for name, option in COMMAND_OPTIONS[args.command].items():
        if not hasattr(args, name):
            setattr(args, name, from_config.get(name, option.default))


def _require_display_yaml_file(args: argparse.Namespace) -> None:
    if args.command != "display" or args.yaml_file is not None:
        return
    print(
        "ERROR: display requires --yaml_file, or 'yaml_file' in the display "
        "section of the config file.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def cli_input() -> argparse.Namespace:
    args = _build_parser().parse_args()
    _apply_config_defaults(args)
    _require_display_yaml_file(args)
    return args


def _validate_ping_ip(ping_ip: str) -> bool:
    if is_valid_host(ping_ip):
        return True
    print(
        "ERROR: Invalid --ping_ip value '{}', "
        "expected an IP address or hostname.".format(ping_ip),
        file=sys.stderr,
    )
    return False


def _validate_ping_count(count: Optional[int]) -> bool:
    if count is None or count >= 1:
        return True
    print(
        "ERROR: Invalid --ping_count value '{}', "
        "expected a positive number of packets.".format(count),
        file=sys.stderr,
    )
    return False


def _validate_trace_hop_ping_count(count: Optional[int]) -> bool:
    if count is None or count >= 1:
        return True
    print(
        "ERROR: Invalid --trace_hop_ping_count value '{}', "
        "expected a positive number of packets.".format(count),
        file=sys.stderr,
    )
    return False


def _resolve_trace_hop_ping_count(count: Optional[int]) -> int:
    """Hop packet count to use, filling in the root-aware default if unset."""
    if count is None:
        return default_hop_ping_count()
    return count


def _run_ping_tests(
    args: argparse.Namespace, test_result: TestResult
) -> Tuple[int, int]:
    if args.skip_pingtest:
        return 0, 0

    logger.debug("Running PingTest")
    attempted = 1
    succeeded = 0

    test_result.ping_result = PingResult.run_test(args.ping_ip, args.ping_count)
    logger.debug("Ping Result: %s", test_result.ping_result)

    if test_result.ping_result is not None:
        succeeded = 1

    if (
        test_result.ping_result is None
        or test_result.ping_result.packet_loss > args.max_packet_loss
    ):
        logger.debug("Running TraceTest")
        hop_count = _resolve_trace_hop_ping_count(args.trace_hop_ping_count)
        test_result.trace_result = TraceResult.run_test(args.ping_ip, hop_count)

    return attempted, succeeded


def _run_speedtest(
    args: argparse.Namespace, test_result: TestResult
) -> Tuple[int, int]:
    if args.skip_speedtest:
        return 0, 0

    # A missing speedtest CLI is reported by check() and treated as a skipped
    # test rather than a failed one.
    if not SpeedResult.check():
        return 0, 0

    logger.debug("Running SpeedTest")
    test_result.speed_result = SpeedResult.run_test()
    if test_result.speed_result is None:
        return 1, 0
    return 1, 1


def _log_yaml_results(args: argparse.Namespace, test_result: TestResult) -> int:
    if args.yaml_file is None:
        return 0

    logger.debug("Logging results to: %s", args.yaml_file)
    try:
        with open(args.yaml_file, "a", encoding="utf-8") as yaml_file:
            print("---\n{}\n...\n".format(test_result.to_yaml()), file=yaml_file)
    except OSError as error:
        print(
            "ERROR: Unable to write results to '{}': {}".format(args.yaml_file, error),
            file=sys.stderr,
        )
        return 1
    return 0


def run(args: argparse.Namespace) -> int:
    logger.debug("%s", datetime.now())

    if not _validate_ping_ip(args.ping_ip):
        return 1

    if not _validate_ping_count(args.ping_count):
        return 1

    if not _validate_trace_hop_ping_count(args.trace_hop_ping_count):
        return 1

    logger.debug("Running Tests")
    test_result = TestResult(ping_result=None, trace_result=None, speed_result=None)

    attempted, succeeded = _run_ping_tests(args, test_result)
    speed_attempted, speed_succeeded = _run_speedtest(args, test_result)
    attempted += speed_attempted
    succeeded += speed_succeeded

    test_result.human_readable(sys.stdout)

    if _log_yaml_results(args, test_result) != 0:
        return 1

    if attempted > 0 and succeeded == 0:
        print("ERROR: All requested tests failed.", file=sys.stderr)
        return 1

    return 0


def _display_thresholds(args: argparse.Namespace) -> RenderThresholds:
    """The healthy thresholds the HTML report draws and colors against."""
    return RenderThresholds(
        download_mbps=args.target_download_mbps,
        upload_mbps=args.target_upload_mbps,
        latency_ms=args.target_latency_ms,
        packet_loss_pct=args.target_packet_loss_pct,
    )


def _load_display_results(yaml_file: str) -> Optional[List[TestResult]]:
    """Results to show, or None once the reason they are unreadable is reported."""
    if yaml_file == STDIN_YAML_FILE:
        content = sys.stdin.read()
        if not content.strip():
            print(
                "ERROR: No results on stdin, expected logged results piped into "
                "'--yaml_file {}'.".format(STDIN_YAML_FILE),
                file=sys.stderr,
            )
            return None
        return TestResult.load_yaml(content)

    try:
        return TestResult.load_results(yaml_file)
    except OSError as error:
        print(
            "ERROR: Unable to read results from '{}': {}".format(yaml_file, error),
            file=sys.stderr,
        )
        return None


def _write_html_report(args: argparse.Namespace, results: List[TestResult]) -> int:
    """Write the report to --html_file, or to stdout when it names no file."""
    if args.html_file is None:
        to_html(
            results,
            sys.stdout,
            _display_thresholds(args),
            embed_plotly=args.embed_plotly,
        )
        return 0

    logger.debug("Writing HTML report to: %s", args.html_file)
    try:
        to_html(
            results,
            args.html_file,
            _display_thresholds(args),
            embed_plotly=args.embed_plotly,
        )
    except OSError as error:
        print(
            "ERROR: Unable to write report to '{}': {}".format(args.html_file, error),
            file=sys.stderr,
        )
        return 1
    return 0


def display(args: argparse.Namespace) -> int:
    results = _load_display_results(args.yaml_file)
    if results is None:
        return 1

    if args.format == "html":
        return _write_html_report(args, results)

    # The text summary has nowhere to go but stdout, so an html_file left over
    # from the config file is not worth failing over, only mentioning.
    if args.html_file is not None:
        print(
            "WARNING: Ignoring --html_file '{}', which only applies to "
            "'--format html'.".format(args.html_file),
            file=sys.stderr,
        )
    to_human(results, sys.stdout)

    return 0


def main() -> None:
    args = cli_input()
    configure_logging(args.debug)
    logger.debug("Parsed Args: %s", args)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
