#!/usr/bin/env python3
import argparse
from datetime import datetime
import sys

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult
from internet_troubleshooter.speed_test import SpeedResult
from internet_troubleshooter.result import TestResult
from internet_troubleshooter.utils import debug, is_valid_host


def cli_input():
    parser = argparse.ArgumentParser(description="Test internet connection.")
    parser.add_argument("--debug", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_cmd = subparsers.add_parser("run")

    run_cmd.add_argument("--ping_ip", default="8.8.8.8")
    run_cmd.add_argument("--ping_count", default=None, type=int)
    run_cmd.add_argument("--max_packet_loss", default=3.0, type=float)
    run_cmd.add_argument("--skip_speedtest", action="store_true")
    run_cmd.add_argument("--skip_pingtest", action="store_true")
    run_cmd.add_argument("--yaml_file", default=None, type=str)

    run_cmd.set_defaults(func=run)

    display_cmd = subparsers.add_parser("display")

    display_cmd.add_argument("--yaml_file", required=True)
    display_cmd.add_argument("--format", default="human", choices=["human", "html"])

    display_cmd.set_defaults(func=display)

    return parser.parse_args()


def run(args):
    debug(args.debug, str(datetime.now()))

    if not is_valid_host(args.ping_ip):
        print(
            "ERROR: Invalid --ping_ip value '{}', "
            "expected an IP address or hostname.".format(args.ping_ip),
            file=sys.stderr,
        )
        return 1

    debug(args.debug, "Running Tests")
    test_result = TestResult(pingResult=None, traceResult=None, speedResult=None)

    attempted = 0
    succeeded = 0

    if not args.skip_pingtest:
        debug(args.debug, "Running PingTest")
        attempted += 1
        test_result.pingResult = PingResult.run_test(args.ping_ip, args.ping_count)
        debug(args.debug, "Ping Result: ", test_result.pingResult)

        if test_result.pingResult is not None:
            succeeded += 1

        if (
            test_result.pingResult is None
            or test_result.pingResult.packetLoss > args.max_packet_loss
        ):
            debug(args.debug, "Running TraceTest")
            test_result.traceResult = TraceResult.run_test(
                args.ping_ip, args.ping_count, args.debug
            )

    if not args.skip_speedtest:
        # A missing speedtest CLI is reported by check() and treated as a
        # skipped test rather than a failed one.
        if SpeedResult.check():
            debug(args.debug, "Running SpeedTest")
            attempted += 1
            test_result.speedResult = SpeedResult.run_test()
            if test_result.speedResult is not None:
                succeeded += 1

    test_result.human_readable(sys.stdout)

    if args.yaml_file is not None:
        debug(args.debug, "Logging results to: ", args.yaml_file)
        try:
            with open(args.yaml_file, "a", encoding="utf-8") as yaml_file:
                print("---\n{}\n...\n".format(test_result.to_yaml()), file=yaml_file)
        except OSError as error:
            print(
                "ERROR: Unable to write results to '{}': {}".format(
                    args.yaml_file, error
                ),
                file=sys.stderr,
            )
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
    debug(args.debug, "Parsed Args: ", args)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
