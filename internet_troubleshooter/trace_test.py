import logging
import re
import sys
from dataclasses import dataclass
from typing import List

from internet_troubleshooter.ping_test import PingResult, default_ping_count_for_uid
from internet_troubleshooter.utils import run_command

logger = logging.getLogger(__name__)

OCTET = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
IPV4 = r"{0}(?:\.{0}){{3}}".format(OCTET)

# Hop lines start with the hop number, optionally followed by `*` for probes
# that timed out. In `traceroute -n` output the address then follows directly;
# otherwise it is in parentheses after the resolved hostname, which may itself
# contain digits and dots.
HOP_PAREN_IP_REGEX = re.compile(r"^\s*\d+\s+.*\(({})\)".format(IPV4))
HOP_NUMERIC_IP_REGEX = re.compile(
    r"^\s*\d+\s+(?:\*\s+)*({})(?:\s|$)".format(IPV4),
)

TRACE_TIMEOUT = 120

# Hops are only pinged to locate where loss is introduced, so they default to a
# smaller sample than the primary target: a trace of 20 hops would otherwise
# take 20 times as long as the primary test. Root can afford a larger sample
# because it floods.
DEFAULT_TRACE_HOP_PING_COUNT_ROOT = 50
DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT = 10


def parse_trace_line(line):
    """Return the IP address of a traceroute hop line, or None if there is none."""
    match = HOP_PAREN_IP_REGEX.match(line) or HOP_NUMERIC_IP_REGEX.match(line)
    if match is None:
        return None
    return match.group(1)


def default_hop_ping_count():
    """Packets to send to each hop when --trace_hop_ping_count was not given."""
    return default_ping_count_for_uid(
        DEFAULT_TRACE_HOP_PING_COUNT_ROOT, DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT
    )


@dataclass
class TraceResult:
    ping_results: List[PingResult]

    def to_dict(self):
        return {
            "ping_results": [
                None if ping is None else ping.to_dict() for ping in self.ping_results
            ]
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            ping_results=[
                None if ping is None else PingResult.from_dict(ping)
                for ping in data.get("ping_results") or []
            ]
        )

    @staticmethod
    def execute_test(ip):
        trace_result = run_command(["traceroute", "-n", ip], timeout=TRACE_TIMEOUT)
        if trace_result is None:
            return None
        if trace_result.returncode != 0:
            print(
                "ERROR: Error running traceroute.\n{}".format(trace_result.stderr),
                file=sys.stderr,
            )
            return None
        return trace_result.stdout

    @staticmethod
    def hop_ips(trace_output, target_ip):
        """Addresses of the intermediate hops in a traceroute.

        A single router often answers for several hops, so addresses are
        deduplicated, keeping the order in which they first appear. The target
        itself is excluded because it is covered by the primary ping test.
        """
        hops = list()
        for line in trace_output.splitlines():
            trace_ip = parse_trace_line(line)
            logger.debug("trace_ip: %s", trace_ip)
            if trace_ip is None or trace_ip == target_ip or trace_ip in hops:
                continue
            hops.append(trace_ip)
        return hops

    @staticmethod
    def run_test(ip, hop_count=None):
        logger.debug("Running Traceroute")
        results = TraceResult.execute_test(ip)
        logger.debug("Traceroute: %s", results)
        if results is None:
            return None

        if hop_count is None:
            hop_count = default_hop_ping_count()
        trace_ping_results = list()
        for trace_ip in TraceResult.hop_ips(results, ip):
            trace_ping_result = PingResult.run_test(trace_ip, hop_count)
            if trace_ping_result is not None:
                trace_ping_results.append(trace_ping_result)
        return TraceResult(ping_results=trace_ping_results)
