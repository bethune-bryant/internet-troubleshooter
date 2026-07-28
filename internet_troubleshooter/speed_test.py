import json
import sys
from dataclasses import dataclass, field
from internet_troubleshooter.utils import run_command, summarize

SPEEDTEST_TIMEOUT = 300
SPEEDTEST_HELP_TIMEOUT = 10


@dataclass
class SpeedResult:
    upload: float = field()
    download: float = field()
    latency: float = field()

    def __init__(self, results=None, upload=None, download=None, latency=None):
        """Build from raw speedtest JSON, or directly from parsed values.

        The raw JSON is deliberately not retained: it contains the MAC address,
        local and external IPs, and ISP of the machine running the test.
        """
        if results is not None:
            parsed_result = json.loads(results)
            upload = float(parsed_result["upload"]["bandwidth"]) / 125000
            download = float(parsed_result["download"]["bandwidth"]) / 125000
            latency = float(parsed_result["ping"]["latency"])

        self.upload = upload
        self.download = download
        self.latency = latency

    def to_dict(self):
        return {
            "upload": self.upload,
            "download": self.download,
            "latency": self.latency,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            upload=float(data["upload"]),
            download=float(data["download"]),
            latency=float(data["latency"]),
        )

    def __str__(self):
        return (
            "Download:    {:.2f}Mbps\n"
            "Upload:      {:.2f}Mbps\n"
            "Latency:     {:.2f}ms"
        ).format(
            self.download,
            self.upload,
            self.latency,
        )

    @staticmethod
    def check():
        speedtest_exists = run_command(
            ["speedtest", "-h"], timeout=SPEEDTEST_HELP_TIMEOUT
        )
        if speedtest_exists is None or speedtest_exists.returncode != 0:
            print(
                (
                    "WARNING: speedtest cli not installed.\n"
                    "Unable to test speed.\n"
                    "See: {}"
                ).format("https://www.speedtest.net/apps/cli"),
                file=sys.stderr,
            )
            return False
        return True

    @staticmethod
    def summarize(results):
        download = [result.download for result in results if result is not None]
        upload = [result.upload for result in results if result is not None]
        latency = [result.latency for result in results if result is not None]
        return "{}\n\n{}\n\n{}".format(
            summarize(download, "Download", "Mbps"),
            summarize(upload, "Upload", "Mbps"),
            summarize(latency, "Latency", "ms"),
        )

    @staticmethod
    def execute_test():
        speedtest_result = run_command(
            ["speedtest", "-f", "json"], timeout=SPEEDTEST_TIMEOUT
        )
        if speedtest_result is None:
            return None
        if speedtest_result.returncode != 0:
            print(
                "ERROR: Error running speedtest.\n{}\n{}".format(
                    speedtest_result.stdout, speedtest_result.stderr
                ),
                file=sys.stderr,
            )
            return None
        return speedtest_result.stdout

    @staticmethod
    def run_test():
        results = SpeedResult.execute_test()
        if results is not None:
            return SpeedResult(results)
        return None
