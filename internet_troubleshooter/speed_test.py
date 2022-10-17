#!/usr/bin/env python3
import os
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, fields

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

    def execute_test():
        speedtest_result = subprocess.run(["speedtest", "-f", "json"], capture_output=True, text=True)
        if speedtest_result.returncode != 0:
            print("ERROR: Error running speedtest.\n{}".format(speedtest_result.stderr), file=sys.stderr)
            exit(4)
        return speedtest_result.stdout

    def run_test():
        speedtest_result = SpeedResult(SpeedResult.execute_test())
        return speedtest_result
