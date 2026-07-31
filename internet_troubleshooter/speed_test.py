from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, cast

from internet_troubleshooter.utils import run_command, summarize

SPEEDTEST_TIMEOUT = 300
SPEEDTEST_HELP_TIMEOUT = 10

# The speedtest CLI reports bandwidth in bytes per second; Mbps is
# bytes/sec * 8 / 1e6, which is the same as dividing by 125,000.
BYTES_PER_SEC_TO_MBPS = 125_000

# Pads the labels in the human readable summary so the values line up.
LABEL_WIDTH = 13


@dataclass
class SpeedResult:
    upload: float
    download: float
    latency: float

    def __init__(
        self,
        results: Optional[str] = None,
        upload: Optional[float] = None,
        download: Optional[float] = None,
        latency: Optional[float] = None,
    ) -> None:
        """Build from raw speedtest JSON, or directly from parsed values.

        The raw JSON is deliberately not retained: it contains the MAC address,
        local and external IPs, and ISP of the machine running the test.

        Raises ValueError when results is not usable speedtest JSON.
        """
        if results is not None:
            upload, download, latency = SpeedResult.parse_result(results)

        # The values are optional only because the two construction paths
        # supply them differently; the fields themselves always hold a float.
        self.upload = cast(float, upload)
        self.download = cast(float, download)
        self.latency = cast(float, latency)

    @staticmethod
    def parse_result(results: str) -> Tuple[float, float, float]:
        """Return (upload, download, latency) from raw speedtest JSON."""
        try:
            parsed_result = json.loads(results)
            return (
                float(parsed_result["upload"]["bandwidth"]) / BYTES_PER_SEC_TO_MBPS,
                float(parsed_result["download"]["bandwidth"]) / BYTES_PER_SEC_TO_MBPS,
                float(parsed_result["ping"]["latency"]),
            )
        except (ValueError, KeyError, TypeError) as error:
            print(
                "ERROR: Unable to parse speedtest output: {}".format(error),
                file=sys.stderr,
            )
            raise ValueError("Malformed speedtest JSON output.") from error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "upload": self.upload,
            "download": self.download,
            "latency": self.latency,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SpeedResult:
        return cls(
            upload=float(data["upload"]),
            download=float(data["download"]),
            latency=float(data["latency"]),
        )

    def __str__(self) -> str:
        return "\n".join(
            [
                "{:<{}}{:.2f}Mbps".format("Download:", LABEL_WIDTH, self.download),
                "{:<{}}{:.2f}Mbps".format("Upload:", LABEL_WIDTH, self.upload),
                "{:<{}}{:.2f}ms".format("Latency:", LABEL_WIDTH, self.latency),
            ]
        )

    @staticmethod
    def check() -> bool:
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
    def summarize(results: Sequence[Optional[SpeedResult]]) -> str:
        download = [result.download for result in results if result is not None]
        upload = [result.upload for result in results if result is not None]
        latency = [result.latency for result in results if result is not None]
        return "{}\n\n{}\n\n{}".format(
            summarize(download, "Download", "Mbps"),
            summarize(upload, "Upload", "Mbps"),
            summarize(latency, "Latency", "ms"),
        )

    @staticmethod
    def execute_test() -> Optional[str]:
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
    def run_test() -> Optional[SpeedResult]:
        results = SpeedResult.execute_test()
        if results is None:
            return None
        try:
            return SpeedResult(results)
        except ValueError:
            return None
