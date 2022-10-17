#!/usr/bin/env python3
import io
import os
import argparse
import re
import subprocess
import sys
import json
from time import time
from typing import Dict, List
from dataclasses import dataclass, field, fields
import yaml
from yaml.loader import UnsafeLoader

from ping_test import PingResult, ping_test

TRACE_IP_REGEX = re.compile(r"^\s*\d+\s*(\S+)\s+.*$")

@dataclass
class TraceResult:
    pingResults: List[PingResult] = field()

@dataclass
class SpeedResult:
    result: str = field()
    upload: float = field()
    download: float = field()
    latency: float = field()


    def __init__(self, results):
        self.result = results
        parsed_result = json.loads(results)
        self.upload = float(parsed_result["upload"]["bandwidth"]) / 125000
        self.download = float(parsed_result["download"]["bandwidth"]) / 125000
        self.latency = float(parsed_result["ping"]["latency"])

@dataclass
class TestResult:
    pingResult: PingResult = field()
    traceResult: TraceResult = field()
    speedResult: SpeedResult = field()
    timeStamp: float = time()

    def human_readable(self, io_target):
        if self.pingResult is not None:
            print("Packet Loss: {:.2f}%".format(self.pingResult.packetLoss), file=io_target)
        
        if self.traceResult is not None:
            for trace_result in self.traceResult.pingResults:
                trace_loss = trace_result.packetLoss
                if trace_loss > 0:
                    print("{:.2f}% {}".format(trace_loss, trace_result.ip), file=io_target)

        if self.speedResult is not None:
            print("Download:    {:.2f}Mbps\nUpload:      {:.2f}Mbps\nLatency:     {:.2f}ms".format(self.speedResult.download, self.speedResult.upload, self.speedResult.latency), file=io_target)

    def to_yaml(self):
        return yaml.dump(self)

def cli_input():
    parser = argparse.ArgumentParser(description='Test internet connection.')

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_cmd = subparsers.add_parser("run")

    run_cmd.add_argument("--ping_ip", default = "8.8.8.8")
    run_cmd.add_argument("--ping_count", default = None, type = int)
    run_cmd.add_argument("--max_packet_loss", default = 3.0, type = float)
    run_cmd.add_argument("--skip_speedtest", action="store_true")
    run_cmd.add_argument("--skip_pingtest", action="store_true")
    run_cmd.add_argument("--min_download", default = 50.0, type = float)
    run_cmd.add_argument("--min_upload", default = 15.0, type = float)

    run_cmd.set_defaults(func=run)

    return parser.parse_args()

def trace_test(ip, count=None):
    uid = os.geteuid()

    if count is None:
        count = 400 if uid == 0 else 10

    trace_result = subprocess.run(["traceroute", ip], capture_output=True, text=True)
    if trace_result.returncode != 0:
        print("ERROR: Error running traceroute.\n{}".format(trace_result.stderr), file=sys.stderr)
        exit(3)
    trace_ping_results = list()
    for line in trace_result.stdout.splitlines():
        trace_match = TRACE_IP_REGEX.search(line)
        if trace_match:
            trace_ip = trace_match.group(1)
            trace_ping_result = ping_test(trace_ip, count)
            trace_ping_results.append(trace_ping_result)
    return TraceResult(pingResults=trace_ping_results)

def speed_test():
    speedtest_result = subprocess.run(["speedtest", "-f", "json"], capture_output=True, text=True)
    if speedtest_result.returncode != 0:
        print("ERROR: Error running speedtest.\n{}".format(speedtest_result.stderr), file=sys.stderr)
        exit(4)
    speedtest_result = SpeedResult(speedtest_result.stdout)
    return speedtest_result

def run(args):
    test_result = TestResult(pingResult = None, traceResult = None, speedResult=None)

    if not args.skip_pingtest:
        test_result.pingResult = ping_test(args.ping_ip, args.ping_count)

        if test_result.pingResult.packetLoss > args.max_packet_loss:
            test_result.traceResult = trace_test(args.ping_ip, args.ping_count)

    if not args.skip_speedtest:
        test_result.speedResult = speed_test()

    #test_result.human_readable(sys.stdout)
    print(yaml.load(test_result.to_yaml(), Loader=UnsafeLoader))

def main():
    args = cli_input()

    args.func(args)

if __name__ == "__main__":
    main()