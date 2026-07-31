from __future__ import annotations

import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

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

TRACEROUTE = "traceroute"

# Debian and Ubuntu package two unrelated traceroute implementations: the
# classic one, which takes -n to skip reverse lookups, and the inetutils one,
# which reports numeric addresses by default and whose packaged version rejects
# -n outright. The help text is the cheapest way to tell them apart.
NUMERIC_HELP_TIMEOUT = 5
NUMERIC_HELP_REGEX = re.compile(r"(?:^|\s)(?:-n|--numeric)(?![\w-])", re.MULTILINE)
NUMERIC_REJECTED_REGEX = re.compile(
    r"(?:invalid|unrecognized|unknown)\s+option.*\b(?:n|numeric)\b",
    re.IGNORECASE,
)

# True when -n is accepted, False when it is not, and None while unprobed or
# when traceroute could not be run at all.
_numeric_supported: Optional[bool] = None

# Hops are only pinged to locate where loss is introduced, so they default to a
# smaller sample than the primary target: a trace of 20 hops would otherwise
# take 20 times as long as the primary test. Root can afford a larger sample
# because it floods.
DEFAULT_TRACE_HOP_PING_COUNT_ROOT = 50
DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT = 10


def parse_trace_line(line: str) -> Optional[str]:
    """Return the IP address of a traceroute hop line, or None if there is none."""
    match = HOP_PAREN_IP_REGEX.match(line) or HOP_NUMERIC_IP_REGEX.match(line)
    if match is None:
        return None
    return match.group(1)


def _probe_numeric_support() -> Optional[bool]:
    """Ask traceroute for its help text and look for -n in it.

    Returns None when traceroute could not be run, in which case run_command has
    already reported why.
    """
    help_result = run_command([TRACEROUTE, "--help"], timeout=NUMERIC_HELP_TIMEOUT)
    if help_result is None:
        return None
    help_text = "{}\n{}".format(help_result.stdout or "", help_result.stderr or "")
    return NUMERIC_HELP_REGEX.search(help_text) is not None


def _cache_numeric_support(supported: Optional[bool]) -> None:
    global _numeric_supported
    _numeric_supported = supported


def _traceroute_supports_numeric() -> Optional[bool]:
    """Whether the installed traceroute accepts -n, probing at most once.

    Which traceroute is installed cannot change while the process runs, and a
    trace pings every hop it finds, so the answer is cached.
    """
    if _numeric_supported is None:
        _cache_numeric_support(_probe_numeric_support())
        logger.debug("traceroute -n supported: %s", _numeric_supported)
    return _numeric_supported


def _traceroute_command(ip: str) -> List[str]:
    """The traceroute invocation for ip, using -n only where it is supported."""
    if _traceroute_supports_numeric():
        return [TRACEROUTE, "-n", ip]
    return [TRACEROUTE, ip]


def _numeric_option_rejected(result: "subprocess.CompletedProcess[str]") -> bool:
    """True when traceroute failed because it does not know the -n option."""
    return (
        result.returncode != 0
        and NUMERIC_REJECTED_REGEX.search(result.stderr or "") is not None
    )


def _run_traceroute(ip: str) -> Optional["subprocess.CompletedProcess[str]"]:
    """Trace to ip, retrying without -n if the binary turns out to reject it.

    The help text and the binary that ends up running can disagree, so a
    rejected -n overrides the probe rather than failing the trace.
    """
    if _traceroute_supports_numeric() is None:
        return None

    command = _traceroute_command(ip)
    logger.debug("Traceroute command: %s", command)
    result = run_command(command, timeout=TRACE_TIMEOUT)
    if result is None or "-n" not in command or not _numeric_option_rejected(result):
        return result

    _cache_numeric_support(False)
    retry = _traceroute_command(ip)
    logger.debug("traceroute rejected -n, retrying as: %s", retry)
    return run_command(retry, timeout=TRACE_TIMEOUT)


def default_hop_ping_count() -> int:
    """Packets to send to each hop when --trace_hop_ping_count was not given."""
    return default_ping_count_for_uid(
        DEFAULT_TRACE_HOP_PING_COUNT_ROOT, DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT
    )


@dataclass
class TraceResult:
    ping_results: List[Optional[PingResult]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ping_results": [
                None if ping is None else ping.to_dict() for ping in self.ping_results
            ]
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TraceResult:
        return cls(
            ping_results=[
                None if ping is None else PingResult.from_dict(ping)
                for ping in data.get("ping_results") or []
            ]
        )

    @staticmethod
    def execute_test(ip: str) -> Optional[str]:
        trace_result = _run_traceroute(ip)
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
    def hop_ips(trace_output: str, target_ip: str) -> List[str]:
        """Addresses of the intermediate hops in a traceroute.

        A single router often answers for several hops, so addresses are
        deduplicated, keeping the order in which they first appear. The target
        itself is excluded because it is covered by the primary ping test.
        """
        hops: List[str] = list()
        for line in trace_output.splitlines():
            trace_ip = parse_trace_line(line)
            logger.debug("trace_ip: %s", trace_ip)
            if trace_ip is None or trace_ip == target_ip or trace_ip in hops:
                continue
            hops.append(trace_ip)
        return hops

    @staticmethod
    def run_test(ip: str, hop_count: Optional[int] = None) -> Optional[TraceResult]:
        logger.debug("Running Traceroute")
        results = TraceResult.execute_test(ip)
        logger.debug("Traceroute: %s", results)
        if results is None:
            return None

        if hop_count is None:
            hop_count = default_hop_ping_count()
        trace_ping_results: List[Optional[PingResult]] = list()
        for trace_ip in TraceResult.hop_ips(results, ip):
            trace_ping_result = PingResult.run_test(trace_ip, hop_count)
            if trace_ping_result is not None:
                trace_ping_results.append(trace_ping_result)
        return TraceResult(ping_results=trace_ping_results)
