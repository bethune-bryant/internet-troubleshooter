import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, fields
from typing import Dict, List

from internet_troubleshooter.ping_test import PingResult

TRACE_IP_REGEX = re.compile(r"^.+?((?:\d+\.){3}\d+).+$")


@dataclass
class TraceResult:
    pingResults: List[PingResult] = field()

    def execute_test(ip, count=None, debug=False):
        trace_result = subprocess.run(
            ["traceroute", ip], capture_output=True, text=True
        )
        if trace_result.returncode != 0:
            print(
                "ERROR: Error running traceroute.\n{}".format(trace_result.stderr),
                file=sys.stderr,
            )
            return None
        return trace_result.stdout

    def run_test(ip, count=None, debug=False):
        if(debug):
            print("Running Traceroute", file=sys.stderr)
        results = TraceResult.execute_test(ip, count, debug)
        if(debug):
            print("Traceroute: ", results, file=sys.stderr)
        if results is not None:
            trace_ping_results = list()
            for line in results.splitlines():
                trace_match = TRACE_IP_REGEX.search(line)
                if(debug):
                    print("trace_match: ", trace_match, file=sys.stderr)
                if trace_match:
                    trace_ip = trace_match.group(1)
                    if trace_ip == ip:
                        continue
                    if(debug):
                        print("trace_ip: ", trace_ip, file=sys.stderr)
                    trace_ping_result = PingResult.run_test(trace_ip, count)
                    trace_ping_results.append(trace_ping_result)
            return TraceResult(pingResults=trace_ping_results)
        return None
