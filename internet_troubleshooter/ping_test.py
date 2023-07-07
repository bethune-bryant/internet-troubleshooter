import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, fields
from internet_troubleshooter.utils import summarize

PACKET_LOSS_REGEX = re.compile(r"([\d.]+)%\s+packet\s+loss")


@dataclass
class PingResult:
    ip: str = field()
    packetLoss: float = field()

    def __str__(self):
        return "{:.2f}%: {}".format(self.packetLoss, self.ip)

    def parse_result(ip, result):
        packet_loss_match = PACKET_LOSS_REGEX.search(result)
        if packet_loss_match is None:
            return None
        return PingResult(ip=ip, packetLoss=float(packet_loss_match.group(1)))
    
    def summarize(results):
        packetLoss = [
            result.packetLoss
            for result in results
            if result is not None
        ]
        return "{}".format(summarize(packetLoss, "Packet Loss", "%"))

    def execute_test(ip, count=None):
        uid = os.geteuid()

        if count is None:
            count = 400 if uid == 0 else 10

        if uid == 0:
            ping_result = subprocess.run(
                ["ping", "-f", "-q", "-c", str(count), ip],
                capture_output=True,
                text=True,
            )
        else:
            print(
                "WARNING: Script not run as root, unable to flood ping.",
                file=sys.stderr,
            )
            ping_result = subprocess.run(
                ["ping", "-q", "-c", str(count), ip], capture_output=True, text=True
            )

        return ping_result.stdout

    def run_test(ip, count=None):
        output = PingResult.execute_test(ip, count)
        result = PingResult.parse_result(ip, output)
        if result is None:
            print(
                "ERROR: Cannot find packet loss in ping test.\n{}".format(output),
                file=sys.stderr,
            )

        return result
