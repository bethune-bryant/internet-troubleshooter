#!/usr/bin/env python3
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, fields
from typing import Dict, List

from internet_troubleshooter.ping_test import PingResult

TRACE_IP_REGEX = re.compile(r"^\s*\d+\s*(\S+)\s+.*$")

@dataclass
class TraceResult:
    pingResults: List[PingResult] = field()

    def execute_test(ip, count=None):
        trace_result = subprocess.run(["traceroute", ip], capture_output=True, text=True)
        if trace_result.returncode != 0:
            print("ERROR: Error running traceroute.\n{}".format(trace_result.stderr), file=sys.stderr)
            return None
        return trace_result.stdout

    def run_test(ip, count=None):
        results = TraceResult.execute_test(ip, count)
        if results is not None:
            trace_ping_results = list()
            for line in results.splitlines():
                trace_match = TRACE_IP_REGEX.search(line)
                if trace_match:
                    trace_ip = trace_match.group(1)
                    trace_ping_result = PingResult.run_test(trace_ip, count)
                    trace_ping_results.append(trace_ping_result)
            return TraceResult(pingResults=trace_ping_results)
        return None
