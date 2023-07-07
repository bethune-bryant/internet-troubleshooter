import os
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, fields
from internet_troubleshooter.utils import summarize


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

    def __str__(self):
        return "Download:    {:.2f}Mbps\nUpload:      {:.2f}Mbps\nLatency:     {:.2f}ms".format(
            self.download,
            self.upload,
            self.latency,
        )
    
    def summarize(results):
        download = [
            result.download
            for result in results
            if result is not None
        ]
        upload = [
            result.upload
            for result in results
            if result is not None
        ]
        latency = [
            result.latency
            for result in results
            if result is not None
        ]
        return "{}\n\n{}\n\n{}".format(summarize(download, "Download", "Mbps"), summarize(upload, "Upload", "Mbps"), summarize(latency, "Latency", "Mbps"))

    def execute_test():
        speedtest_result = subprocess.run(
            ["speedtest", "-f", "json"], capture_output=True, text=True
        )
        if speedtest_result.returncode != 0:
            print(
                "ERROR: Error running speedtest.\n{}\n{}".format(
                    speedtest_result.stdout, speedtest_result.stderr
                ),
                file=sys.stderr,
            )
            return None
        return speedtest_result.stdout

    def run_test():
        results = SpeedResult.execute_test()
        if results is not None:
            return SpeedResult(results)
        return None
