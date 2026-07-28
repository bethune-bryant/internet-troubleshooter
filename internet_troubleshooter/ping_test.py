import os
import re
import sys
from dataclasses import dataclass, field
from internet_troubleshooter.utils import run_command, summarize

PACKET_LOSS_REGEX = re.compile(r"([\d.]+)%\s+packet\s+loss")

PING_TIMEOUT = 120


@dataclass
class PingResult:
    ip: str = field()
    packetLoss: float = field()

    def __str__(self):
        return "{:.2f}%: {}".format(self.packetLoss, self.ip)

    def to_dict(self):
        return {"ip": self.ip, "packetLoss": self.packetLoss}

    @classmethod
    def from_dict(cls, data):
        return cls(ip=data["ip"], packetLoss=float(data["packetLoss"]))

    @staticmethod
    def parse_result(ip, result):
        packet_loss_match = PACKET_LOSS_REGEX.search(result)
        if packet_loss_match is None:
            return None
        return PingResult(ip=ip, packetLoss=float(packet_loss_match.group(1)))

    @staticmethod
    def summarize(results):
        packetLoss = [result.packetLoss for result in results if result is not None]
        return "{}".format(summarize(packetLoss, "Packet Loss", "%"))

    @staticmethod
    def execute_test(ip, count=None):
        uid = os.geteuid()

        if count is None:
            count = 400 if uid == 0 else 10

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
    def run_test(ip, count=None):
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
