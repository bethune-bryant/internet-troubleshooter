#!/usr/bin/env python3
import io
import os
import argparse
import re
import subprocess
import sys
import json
from time import time
from datetime import datetime
from typing import Dict, List
from dataclasses import dataclass, field, fields
import yaml
from yaml.loader import UnsafeLoader

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult
from internet_troubleshooter.speed_test import SpeedResult

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
    
    def load_results(yaml_filename):
        with open(yaml_filename) as f:
            return yaml.load_all(f.read(), Loader=UnsafeLoader)

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
    run_cmd.add_argument("--format", default = "human", choices=["human", "yaml"])

    run_cmd.set_defaults(func=run)

    display_cmd = subparsers.add_parser("display")

    display_cmd.add_argument("--yaml_file", required=True)

    display_cmd.set_defaults(func=display)

    return parser.parse_args()

def run(args):
    test_result = TestResult(pingResult = None, traceResult = None, speedResult=None)

    if not args.skip_pingtest:
        test_result.pingResult = PingResult.run_test(args.ping_ip, args.ping_count)

        if test_result.pingResult.packetLoss > args.max_packet_loss:
            test_result.traceResult = TraceResult.run_test(args.ping_ip, args.ping_count)

    if not args.skip_speedtest:
        test_result.speedResult = SpeedResult.run_test()

    if args.format == "human":
        test_result.human_readable(sys.stdout)
    else:
        print("---\n{}\n...\n".format(test_result.to_yaml()))

def display(args):
    from plotly import graph_objs as go
    from plotly.subplots import make_subplots

    results = list(TestResult.load_results(args.yaml_file))

    results.sort(key=lambda x: x.timeStamp)

    xs = [datetime.fromtimestamp(result.timeStamp) for result in results]
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Scatter(x=xs, y=[result.speedResult.download for result in results], name="Download"), secondary_y=False)
    fig.add_trace(go.Scatter(x=xs, y=[50]*len(results), name="50Mbps"), secondary_y=False)

    fig.add_trace(go.Scatter(x=xs, y=[result.speedResult.upload for result in results], name="Upload"), secondary_y=False)
    fig.add_trace(go.Scatter(x=xs, y=[15]*len(results), name="15Mbps"), secondary_y=False)
    
    fig.add_trace(go.Scatter(x=xs, y=[result.speedResult.latency for result in results], name="Latency"), secondary_y=True)
    fig.add_trace(go.Scatter(x=xs, y=[20]*len(results), name="20ms"), secondary_y=True)

    fig.update_layout(
        title_text="Internet Status"
    )

    fig.update_xaxes(title_text="Test Time")

    fig.update_yaxes(title_text="Internet Speed(Mbps)", rangemode="tozero", secondary_y=False)
    fig.update_yaxes(title_text="Latency(ms)", rangemode="tozero", secondary_y=True)

    fig.write_html(sys.stdout,
                full_html=True,
                include_plotlyjs='cdn')


def main():
    args = cli_input()

    args.func(args)

if __name__ == "__main__":
    main()