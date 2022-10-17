#!/usr/bin/env python3
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, fields

PACKET_LOSS_REGEX = re.compile(r"([\d.]+)%\s+packet\s+loss")

@dataclass
class PingResult:
    ip: str = field()
    packetLoss: float = field()

def ping_test(ip, count=None):
    uid = os.geteuid()

    if count is None:
        count = 400 if uid == 0 else 10

    if uid == 0:
        ping_result = subprocess.run(["ping", "-f", "-q", "-c", str(count), ip], capture_output=True, text=True)
    else:
        print("WARNING: Script not run as root, unable to flood ping.", file=sys.stderr)
        ping_result = subprocess.run(["ping", "-q", "-c", str(count), ip], capture_output=True, text=True)

    packet_loss_match = PACKET_LOSS_REGEX.search(ping_result.stdout)
    if packet_loss_match is None:
        print("ERROR: Cannot find packet loss in ping test.\n{}\n{}".format(ping_result.stdout, ping_result.stderr), file=sys.stderr)
        exit(2)
    
    return PingResult(ip=ip, packetLoss=float(packet_loss_match.group(1)))