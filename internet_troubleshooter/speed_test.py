from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, cast

from internet_troubleshooter.utils import LABEL_WIDTH, run_command, summarize

SPEEDTEST_TIMEOUT = 300
SPEEDTEST_HELP_TIMEOUT = 10

# The speedtest CLI reports bandwidth in bytes per second; Mbps is
# bytes/sec * 8 / 1e6, which is the same as dividing by 125,000.
BYTES_PER_SEC_TO_MBPS = 125_000


@dataclass
class SpeedResult:
    upload: float
    download: float
    latency: float
    raw_result: Optional[Dict[str, Any]] = None

    def __init__(
        self,
        results: Optional[str] = None,
        upload: Optional[float] = None,
        download: Optional[float] = None,
        latency: Optional[float] = None,
        raw_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Build from raw speedtest JSON, or directly from parsed values.

        The complete parsed JSON is kept in raw_result so that a logged run
        records everything the speedtest CLI reported, including the server it
        reached, the ISP, and the MAC address and IPs of this machine.

        Raises ValueError when results is not usable speedtest JSON.
        """
        if results is not None:
            raw_result, upload, download, latency = SpeedResult.parse_result(results)

        # The values are optional only because the two construction paths
        # supply them differently; the fields themselves always hold a float.
        self.upload = cast(float, upload)
        self.download = cast(float, download)
        self.latency = cast(float, latency)
        self.raw_result = raw_result

    @staticmethod
    def parse_result(results: str) -> Tuple[Dict[str, Any], float, float, float]:
        """Return the whole parsed JSON and its (upload, download, latency)."""
        try:
            parsed_result = json.loads(results)
            return (
                cast(Dict[str, Any], parsed_result),
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
        data: Dict[str, Any] = {
            "upload": self.upload,
            "download": self.download,
            "latency": self.latency,
        }
        # Results built from explicit measurements have no JSON behind them,
        # and writing the key as null would only pad every logged document.
        if self.raw_result is not None:
            data["raw_result"] = self.raw_result
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SpeedResult:
        raw_result = data.get("raw_result")
        return cls(
            upload=float(data["upload"]),
            download=float(data["download"]),
            latency=float(data["latency"]),
            raw_result=None if raw_result is None else dict(raw_result),
        )

    def _raw_value(self, *keys: str) -> Optional[str]:
        """A nested value from the raw JSON as text, or None when it is absent."""
        value: Any = self.raw_result
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if value is None or value == "":
            return None
        return str(value)

    @property
    def server(self) -> Optional[str]:
        """The test server as 'name (location)', from whichever parts are known."""
        name = self._raw_value("server", "name")
        location = self._raw_value("server", "location")
        if name is None:
            return location
        if location is None:
            return name
        return "{} ({})".format(name, location)

    @property
    def isp(self) -> Optional[str]:
        return self._raw_value("isp")

    @property
    def external_ip(self) -> Optional[str]:
        return self._raw_value("interface", "externalIp")

    def context(self) -> List[Tuple[str, str]]:
        """Labelled details of where the test ran, for display alongside it.

        Empty unless the raw JSON was kept and holds the value in question.
        """
        details = [
            ("Server", self.server),
            ("ISP", self.isp),
            ("External IP", self.external_ip),
        ]
        return [(label, value) for label, value in details if value is not None]

    def __str__(self) -> str:
        lines = [
            "{:<{}}{:.2f}Mbps".format("Download:", LABEL_WIDTH, self.download),
            "{:<{}}{:.2f}Mbps".format("Upload:", LABEL_WIDTH, self.upload),
            "{:<{}}{:.2f}ms".format("Latency:", LABEL_WIDTH, self.latency),
        ]
        lines.extend(
            "{:<{}}{}".format("{}:".format(label), LABEL_WIDTH, value)
            for label, value in self.context()
        )
        return "\n".join(lines)

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
