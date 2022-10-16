#!/usr/bin/env python3
import os
import argparse
import re
import subprocess
import sys
import json
from typing import Dict, List
from dataclasses import dataclass, field, fields

PACKET_LOSS_REGEX = re.compile(r"([\d.]+)%\s+packet\s+loss")
TRACE_IP_REGEX = re.compile(r"^\s*\d+\s*(\S+)\s+.*$")

@dataclass
class PingResult:
    ip: str = field(repr=False)
    packetLoss: float = field(repr=False)

@dataclass
class TraceResult:
    pingResults: List[PingResult] = field(repr=False)

@dataclass
class SpeedResult:
    result: Dict = field(repr=False)

    def upload(self):
        return float(self.result["upload"]["bandwidth"]) / 125000

    def download(self):
        return float(self.result["download"]["bandwidth"]) / 125000

    def latency(self):
        return float(self.result["ping"]["latency"])

@dataclass
class TestResult:
    pingResult: PingResult = field(repr=False)
    traceResult: TraceResult = field(repr=False)
    speedResult: SpeedResult = field(repr=False)

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

def ping_test(ip, count=None):
    uid = os.geteuid()

    if count is None:
        count = 400 if uid == 0 else 10

    if uid == 0:
        ping_result = subprocess.run(["ping", "-f", "-q", "-c", str(count), ip], capture_output=True, text=True)
    else:
        print("WARNING: Script not run as root, unable to flood ping.", file=sys.stderr)
        ping_result = subprocess.run(["ping", "-q", "-c", str(count), ip], capture_output=True, text=True)

    packet_loss_match = PACKET_LOSS_REGEX.search(ping_result.stdout)
    if packet_loss_match is None:
        print("ERROR: Cannot find packet loss in ping test.\n{}\n{}".format(ping_result.stdout, ping_result.stderr), file=sys.stderr)
        exit(2)
    
    return PingResult(ip=ip, packetLoss=float(packet_loss_match.group(1)))

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
    speedtest_result = json.loads(speedtest_result.stdout)
    return SpeedResult(result = speedtest_result)

def human_readable_output(test_result):
    if test_result.pingResult is not None:
        print("Packet Loss: {:.2f}%".format(test_result.pingResult.packetLoss))
    
    if test_result.traceResult is not None:
        for trace_result in test_result.traceResult.pingResults:
            trace_loss = trace_result.packetLoss
            if trace_loss > 0:
                print("{:.2f}% {}".format(trace_loss, trace_result.ip))

    if test_result.speedResult is not None:
        print("Download:    {:.2f}Mbps\nUpload:      {:.2f}Mbps\nLatency:     {:.2f}ms".format(test_result.speedResult.download(), test_result.speedResult.upload(), test_result.speedResult.latency()))

def run(args):
    test_result = TestResult(pingResult = None, traceResult = None, speedResult=None)

    if not args.skip_pingtest:
        test_result.pingResult = ping_test(args.ping_ip, args.ping_count)

        if test_result.pingResult.packetLoss > args.max_packet_loss:
            test_result.traceResult = trace_test(args.ping_ip, args.ping_count)

    if not args.skip_speedtest:
        test_result.speedResult = speed_test()

    human_readable_output(test_result)

def main():
    args = cli_input()

    args.func(args)

if __name__ == "__main__":
    main()