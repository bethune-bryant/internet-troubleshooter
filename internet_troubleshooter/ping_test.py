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

    def parse_result(ip, result):
        retval = PingResult()
        retval.ip = ip
        packet_loss_match = PACKET_LOSS_REGEX.search(result)
        if packet_loss_match is not None:
            retval.packetLoss=float(packet_loss_match.group(1))
        return retval

def ping_test(ip, count=None):
    uid = os.geteuid()

    if count is None:
        count = 400 if uid == 0 else 10

    if uid == 0:
        ping_result = subprocess.run(["ping", "-f", "-q", "-c", str(count), ip], capture_output=True, text=True)
    else:
        print("WARNING: Script not run as root, unable to flood ping.", file=sys.stderr)
        ping_result = subprocess.run(["ping", "-q", "-c", str(count), ip], capture_output=True, text=True)

    result = parse_result(ip, ping_result.stdout)
    if result is None:
        print("ERROR: Cannot find packet loss in ping test.\n{}\n{}".format(ping_result.stdout, ping_result.stderr), file=sys.stderr)
        exit(2)
    
    return result