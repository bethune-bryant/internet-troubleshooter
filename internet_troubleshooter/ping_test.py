from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence

from internet_troubleshooter.utils import run_command, summarize

PACKET_LOSS_REGEX = re.compile(r"([\d.]+)%\s+packet\s+loss")

# The round trip time line ping prints below the packet loss figure. A flood
# ping appends its own figures to it, so the line is matched rather than
# anchored to its end. The deviation is the last of the four values and is
# absent from builds that do not report it.
RTT_REGEX = re.compile(
    r"(?:rtt|round-trip)\s+min/avg/max(?:/(?:mdev|stddev))?\s*=\s*"
    r"([\d.]+)/([\d.]+)/([\d.]+)(?:/([\d.]+))?\s*ms"
)

PING_TIMEOUT = 120

DEFAULT_PING_COUNT_ROOT = 400
DEFAULT_PING_COUNT_NON_ROOT = 10


def default_ping_count_for_uid(root_count: int, non_root_count: int) -> int:
    """Packet count to use when none was requested.

    Only root may flood ping, so a much larger sample is affordable there.
    """
    return root_count if os.geteuid() == 0 else non_root_count


def _optional_float(value: Any) -> Optional[float]:
    """A measurement as a float, or None where none was recorded."""
    return None if value is None else float(value)


@dataclass
class PingResult:
    """Packet loss to an address, with the round trip times ping measured.

    The round trip figures are optional: a ping that lost every packet reports
    no statistics line, and results logged before they were recorded have none.
    """

    ip: str
    packet_loss: float
    rtt_min_ms: Optional[float] = None
    rtt_avg_ms: Optional[float] = None
    rtt_max_ms: Optional[float] = None
    rtt_mdev_ms: Optional[float] = None

    def __str__(self) -> str:
        return "{:.2f}%: {}".format(self.packet_loss, self.ip)

    def _rtt_dict(self) -> Dict[str, float]:
        """The round trip figures that were measured, keyed as they are logged."""
        measured = {
            "rtt_min_ms": self.rtt_min_ms,
            "rtt_avg_ms": self.rtt_avg_ms,
            "rtt_max_ms": self.rtt_max_ms,
            "rtt_mdev_ms": self.rtt_mdev_ms,
        }
        return {key: value for key, value in measured.items() if value is not None}

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"ip": self.ip, "packet_loss": self.packet_loss}
        # An unmeasured figure is left out rather than written as null, which
        # would only pad every logged document.
        data.update(self._rtt_dict())
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PingResult:
        return cls(
            ip=data["ip"],
            packet_loss=float(data["packet_loss"]),
            rtt_min_ms=_optional_float(data.get("rtt_min_ms")),
            rtt_avg_ms=_optional_float(data.get("rtt_avg_ms")),
            rtt_max_ms=_optional_float(data.get("rtt_max_ms")),
            rtt_mdev_ms=_optional_float(data.get("rtt_mdev_ms")),
        )

    @staticmethod
    def parse_result(ip: str, result: str) -> Optional[PingResult]:
        packet_loss_match = PACKET_LOSS_REGEX.search(result)
        if packet_loss_match is None:
            return None

        packet_loss = float(packet_loss_match.group(1))
        rtt_match = RTT_REGEX.search(result)
        if rtt_match is None:
            return PingResult(ip=ip, packet_loss=packet_loss)

        return PingResult(
            ip=ip,
            packet_loss=packet_loss,
            rtt_min_ms=float(rtt_match.group(1)),
            rtt_avg_ms=float(rtt_match.group(2)),
            rtt_max_ms=float(rtt_match.group(3)),
            rtt_mdev_ms=_optional_float(rtt_match.group(4)),
        )

    @staticmethod
    def summarize(results: Sequence[Optional[PingResult]]) -> str:
        packet_loss = [result.packet_loss for result in results if result is not None]
        rtt_avg = [
            result.rtt_avg_ms
            for result in results
            if result is not None and result.rtt_avg_ms is not None
        ]
        return "{}\n\n{}".format(
            summarize(packet_loss, "Packet Loss", "%"),
            summarize(rtt_avg, "Ping RTT", "ms"),
        )

    @staticmethod
    def execute_test(ip: str, count: Optional[int] = None) -> Optional[str]:
        uid = os.geteuid()

        if count is None:
            count = default_ping_count_for_uid(
                DEFAULT_PING_COUNT_ROOT, DEFAULT_PING_COUNT_NON_ROOT
            )

        if uid == 0:
            command = ["ping", "-f", "-q", "-c", str(count), ip]
        else:
            print(
                "WARNING: Script not run as root, unable to flood ping.",
                "Packet loss may not be accurate.",
                file=sys.stderr,
            )
            command = ["ping", "-q", "-c", str(count), ip]

        ping_result = run_command(command, timeout=PING_TIMEOUT)

        if ping_result is None:
            return None

        return ping_result.stdout

    @staticmethod
    def run_test(ip: str, count: Optional[int] = None) -> Optional[PingResult]:
        output = PingResult.execute_test(ip, count)
        if output is None:
            return None

        result = PingResult.parse_result(ip, output)
        if result is None:
            print(
                "ERROR: Cannot find packet loss in ping test.\n{}".format(output),
                file=sys.stderr,
            )

        return result
