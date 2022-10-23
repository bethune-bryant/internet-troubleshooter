#!/usr/bin/env python3
import argparse
import sys
from statistics import mean

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult
from internet_troubleshooter.speed_test import SpeedResult
from internet_troubleshooter.result import TestResult


def cli_input():
    parser = argparse.ArgumentParser(description="Test internet connection.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_cmd = subparsers.add_parser("run")

    run_cmd.add_argument("--ping_ip", default="8.8.8.8")
    run_cmd.add_argument("--ping_count", default=None, type=int)
    run_cmd.add_argument("--max_packet_loss", default=3.0, type=float)
    run_cmd.add_argument("--skip_speedtest", action="store_true")
    run_cmd.add_argument("--skip_pingtest", action="store_true")
    run_cmd.add_argument("--format", default="human", choices=["human", "yaml"])

    run_cmd.set_defaults(func=run)

    display_cmd = subparsers.add_parser("display")

    display_cmd.add_argument("--yaml_file", required=True)

    display_cmd.set_defaults(func=display)

    return parser.parse_args()


def run(args):
    test_result = TestResult(pingResult=None, traceResult=None, speedResult=None)

    if not args.skip_pingtest:
        test_result.pingResult = PingResult.run_test(args.ping_ip, args.ping_count)

        if test_result.pingResult.packetLoss > args.max_packet_loss:
            test_result.traceResult = TraceResult.run_test(
                args.ping_ip, args.ping_count
            )

    if not args.skip_speedtest:
        test_result.speedResult = SpeedResult.run_test()

    if args.format == "human":
        test_result.human_readable(sys.stdout)
    else:
        print("---\n{}\n...\n".format(test_result.to_yaml()))


def display(args):
    results = list(TestResult.load_results(args.yaml_file))
    TestResult.to_html(results)


def main():
    args = cli_input()

    args.func(args)


if __name__ == "__main__":
    main()
