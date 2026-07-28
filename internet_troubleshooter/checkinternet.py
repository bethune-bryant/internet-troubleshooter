#!/usr/bin/env python3
import argparse
import logging
from datetime import datetime
import sys

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult
from internet_troubleshooter.speed_test import SpeedResult
from internet_troubleshooter.result import TestResult
from internet_troubleshooter.utils import configure_logging, is_valid_host

logger = logging.getLogger(__name__)


def cli_input():
    parser = argparse.ArgumentParser(description="Test internet connection.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print progress and raw command output to stderr.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_cmd = subparsers.add_parser("run", help="Run the tests once.")

    run_cmd.add_argument(
        "--ping_ip",
        default="8.8.8.8",
        help="IP address or hostname to ping. (default: %(default)s)",
    )
    run_cmd.add_argument(
        "--ping_count",
        default=None,
        type=int,
        help="Packets to send. (default: 400 as root, otherwise 10)",
    )
    run_cmd.add_argument(
        "--max_packet_loss",
        default=3.0,
        type=float,
        help="Packet loss percent above which a traceroute is run. "
        "(default: %(default)s)",
    )
    run_cmd.add_argument(
        "--skip_speedtest", action="store_true", help="Do not run the speed test."
    )
    run_cmd.add_argument(
        "--skip_pingtest",
        action="store_true",
        help="Do not run the ping test, and therefore never traceroute.",
    )
    run_cmd.add_argument(
        "--yaml_file",
        default=None,
        type=str,
        help="File to append this run's results to, for later display.",
    )

    run_cmd.set_defaults(func=run)

    display_cmd = subparsers.add_parser(
        "display", help="Summarize results logged by previous runs."
    )

    display_cmd.add_argument(
        "--yaml_file", required=True, help="File of logged results to read."
    )
    display_cmd.add_argument(
        "--format",
        default="human",
        choices=["human", "html"],
        help="Output format, written to stdout. (default: %(default)s)",
    )

    display_cmd.set_defaults(func=display)

    return parser.parse_args()


def _validate_ping_ip(ping_ip):
    if is_valid_host(ping_ip):
        return True
    print(
        "ERROR: Invalid --ping_ip value '{}', "
        "expected an IP address or hostname.".format(ping_ip),
        file=sys.stderr,
    )
    return False


def _validate_ping_count(count):
    if count is None or count >= 1:
        return True
    print(
        "ERROR: Invalid --ping_count value '{}', "
        "expected a positive number of packets.".format(count),
        file=sys.stderr,
    )
    return False


def _run_ping_tests(args, test_result):
    if args.skip_pingtest:
        return 0, 0

    logger.debug("Running PingTest")
    attempted = 1
    succeeded = 0

    test_result.pingResult = PingResult.run_test(args.ping_ip, args.ping_count)
    logger.debug("Ping Result: %s", test_result.pingResult)

    if test_result.pingResult is not None:
        succeeded = 1

    if (
        test_result.pingResult is None
        or test_result.pingResult.packetLoss > args.max_packet_loss
    ):
        logger.debug("Running TraceTest")
        test_result.traceResult = TraceResult.run_test(args.ping_ip, args.ping_count)

    return attempted, succeeded


def _run_speedtest(args, test_result):
    if args.skip_speedtest:
        return 0, 0

    # A missing speedtest CLI is reported by check() and treated as a skipped
    # test rather than a failed one.
    if not SpeedResult.check():
        return 0, 0

    logger.debug("Running SpeedTest")
    test_result.speedResult = SpeedResult.run_test()
    if test_result.speedResult is None:
        return 1, 0
    return 1, 1


def _log_yaml_results(args, test_result):
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


def run(args):
    logger.debug("%s", datetime.now())

    if not _validate_ping_ip(args.ping_ip):
        return 1

    if not _validate_ping_count(args.ping_count):
        return 1

    logger.debug("Running Tests")
    test_result = TestResult(pingResult=None, traceResult=None, speedResult=None)

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


def display(args):
    try:
        results = TestResult.load_results(args.yaml_file)
    except OSError as error:
        print(
            "ERROR: Unable to read results from '{}': {}".format(args.yaml_file, error),
            file=sys.stderr,
        )
        return 1

    if args.format == "html":
        TestResult.to_html(results, sys.stdout)
    else:
        TestResult.to_human(results, sys.stdout)

    return 0


def main():
    args = cli_input()
    configure_logging(args.debug)
    logger.debug("Parsed Args: %s", args)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
