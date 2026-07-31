from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence

from internet_troubleshooter.utils import run_command, summarize

PACKET_LOSS_REGEX = re.compile(r"([\d.]+)%\s+packet\s+loss")

PING_TIMEOUT = 120

DEFAULT_PING_COUNT_ROOT = 400
DEFAULT_PING_COUNT_NON_ROOT = 10


def default_ping_count_for_uid(root_count: int, non_root_count: int) -> int:
    """Packet count to use when none was requested.

    Only root may flood ping, so a much larger sample is affordable there.
    """
    return root_count if os.geteuid() == 0 else non_root_count


@dataclass
class PingResult:
    ip: str
    packet_loss: float

    def __str__(self) -> str:
        return "{:.2f}%: {}".format(self.packet_loss, self.ip)

    def to_dict(self) -> Dict[str, Any]:
        return {"ip": self.ip, "packet_loss": self.packet_loss}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PingResult:
        return cls(ip=data["ip"], packet_loss=float(data["packet_loss"]))

    @staticmethod
    def parse_result(ip: str, result: str) -> Optional[PingResult]:
        packet_loss_match = PACKET_LOSS_REGEX.search(result)
        if packet_loss_match is None:
            return None
        return PingResult(ip=ip, packet_loss=float(packet_loss_match.group(1)))

    @staticmethod
    def summarize(results: Sequence[Optional[PingResult]]) -> str:
        packet_loss = [result.packet_loss for result in results if result is not None]
        return summarize(packet_loss, "Packet Loss", "%")

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
