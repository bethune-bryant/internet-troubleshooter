import logging
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import (
    DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT,
    DEFAULT_TRACE_HOP_PING_COUNT_ROOT,
    TraceResult,
    default_hop_ping_count,
    parse_trace_line,
)

# Abbreviated help output of the two traceroute implementations Debian and
# Ubuntu package; only the classic one lists -n.
CLASSIC_HELP = "\n".join(
    [
        "Usage:",
        "  traceroute [ -46dFITnreAUDV ] [ -f first_ttl ] host",
        "Options:",
        "  -4                          Use IPv4",
        "  -n                          Do not resolve IP addresses",
        "  -q nqueries  --queries=nqueries  Send nqueries probes per hop",
    ]
)
INETUTILS_HELP = "\n".join(
    [
        "Usage: traceroute [OPTION...] HOST",
        "Print the route packets trace to network host.",
        "",
        "  -f, --first-hop=NUM        set initial hop distance",
        "  -m, --max-hop=NUM          set maximal hop count (default: 64)",
        "      --resolve-hostnames    resolve hostnames",
        "  -?, --help                 give this help list",
    ]
)
INVALID_NUMERIC_ERROR = "\n".join(
    [
        "traceroute: invalid option -- 'n'",
        "Try 'traceroute --help' or 'traceroute --usage' for more information.",
    ]
)


@pytest.fixture(autouse=True)
def unprobed_traceroute(mocker):
    """Forget which traceroute is installed, so each test probes on its own."""
    mocker.patch("internet_troubleshooter.trace_test._numeric_supported", None)


def _help_then(*results):
    """subprocess.run results for the -n probe followed by the traces after it."""
    return [CompletedProcess(None, returncode=0, stdout=CLASSIC_HELP), *results]


@pytest.mark.parametrize(
    "line, expected",
    [
        ("3  host-1.2.3.4.5.6.isp.net (203.0.113.9)  10 ms", "203.0.113.9"),
        ("2  1234.5678.9012.3456.example.com (198.51.100.7)", "198.51.100.7"),
        ("5  10.0.0.1", "10.0.0.1"),
        (" 3  203.0.113.9  10.123 ms", "203.0.113.9"),
        (" 1  192.168.1.1  0.310 ms  0.284 ms  0.271 ms", "192.168.1.1"),
        ("12  255.255.255.255  1.0 ms", "255.255.255.255"),
        (" 7  * 203.0.113.9  30.000 ms *", "203.0.113.9"),
        (" 8  * * 198.51.100.7  9.1 ms", "198.51.100.7"),
        (" 9  203.0.113.9  9.1 ms !H", "203.0.113.9"),
        # inetutils-traceroute glues the unit to the time and is numeric by
        # default, so its hop lines have no space before `ms`.
        (" 1  192.168.1.1  8.310ms  8.447ms  8.461ms", "192.168.1.1"),
        (" 2  * 10.0.0.1  12.100ms *", "10.0.0.1"),
        (" 3  gateway (192.168.1.1)  8.310ms", "192.168.1.1"),
    ],
)
def test_parse_trace_line(line, expected):
    assert parse_trace_line(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets",
        " 4  * * *",
        "",
        "   ",
        "7  256.1.2.3  1.0 ms",
        "8  1.2.3  1.0 ms",
    ],
)
def test_parse_trace_line_no_ip(line):
    assert parse_trace_line(line) is None


def test_TraceResult():
    x = TraceResult([PingResult(ip="1.1.1.1", packet_loss=10)])
    assert x.ping_results[0].ip == "1.1.1.1"
    assert x.ping_results[0].packet_loss == 10


def test_execute_test(mocker, capsys):
    test_output = """TEST STRING"""

    mocker.patch(
        "internet_troubleshooter.trace_test._traceroute_supports_numeric",
        return_value=True,
    )
    run = mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(None, returncode=0, stdout=test_output),
    )

    x = TraceResult.execute_test("8.8.8.8")
    assert test_output == x
    assert run.call_args.args[0] == ["traceroute", "-n", "8.8.8.8"]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    "help_output, expected_command",
    [
        (CLASSIC_HELP, ["traceroute", "-n", "8.8.8.8"]),
        (INETUTILS_HELP, ["traceroute", "8.8.8.8"]),
    ],
)
def test_execute_test_picks_command_from_help(
    mocker, capsys, help_output, expected_command
):
    test_output = """TEST STRING"""
    run = mocker.patch(
        "subprocess.run",
        side_effect=[
            CompletedProcess(None, returncode=0, stdout=help_output),
            CompletedProcess(None, returncode=0, stdout=test_output),
        ],
    )

    assert TraceResult.execute_test("8.8.8.8") == test_output
    assert [call.args[0] for call in run.call_args_list] == [
        ["traceroute", "--help"],
        expected_command,
    ]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_execute_test_probes_help_only_once(mocker):
    run = mocker.patch(
        "subprocess.run",
        side_effect=_help_then(
            CompletedProcess(None, returncode=0, stdout="FIRST"),
            CompletedProcess(None, returncode=0, stdout="SECOND"),
        ),
    )

    assert TraceResult.execute_test("8.8.8.8") == "FIRST"
    assert TraceResult.execute_test("8.8.4.4") == "SECOND"
    assert [call.args[0] for call in run.call_args_list] == [
        ["traceroute", "--help"],
        ["traceroute", "-n", "8.8.8.8"],
        ["traceroute", "-n", "8.8.4.4"],
    ]


def test_execute_test_help_reports_numeric_support_at_debug_level(mocker, caplog):
    mocker.patch(
        "subprocess.run",
        side_effect=_help_then(CompletedProcess(None, returncode=0, stdout="TRACE")),
    )

    with caplog.at_level(logging.DEBUG):
        TraceResult.execute_test("8.8.8.8")

    assert "traceroute -n supported: True" in caplog.text
    assert "Traceroute command: ['traceroute', '-n', '8.8.8.8']" in caplog.text


def test_execute_test_retries_without_numeric_option(mocker, capsys, caplog):
    test_output = """TEST STRING"""
    run = mocker.patch(
        "subprocess.run",
        side_effect=_help_then(
            CompletedProcess(
                None, returncode=1, stdout="", stderr=INVALID_NUMERIC_ERROR
            ),
            CompletedProcess(None, returncode=0, stdout=test_output),
        ),
    )

    with caplog.at_level(logging.DEBUG):
        assert TraceResult.execute_test("8.8.8.8") == test_output

    assert [call.args[0] for call in run.call_args_list] == [
        ["traceroute", "--help"],
        ["traceroute", "-n", "8.8.8.8"],
        ["traceroute", "8.8.8.8"],
    ]
    assert "retrying as: ['traceroute', '8.8.8.8']" in caplog.text
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_execute_test_retry_updates_cached_numeric_support(mocker):
    run = mocker.patch(
        "subprocess.run",
        side_effect=_help_then(
            CompletedProcess(
                None, returncode=1, stdout="", stderr=INVALID_NUMERIC_ERROR
            ),
            CompletedProcess(None, returncode=0, stdout="FIRST"),
            CompletedProcess(None, returncode=0, stdout="SECOND"),
        ),
    )

    assert TraceResult.execute_test("8.8.8.8") == "FIRST"
    assert TraceResult.execute_test("8.8.4.4") == "SECOND"
    assert [call.args[0] for call in run.call_args_list] == [
        ["traceroute", "--help"],
        ["traceroute", "-n", "8.8.8.8"],
        ["traceroute", "8.8.8.8"],
        ["traceroute", "8.8.4.4"],
    ]


def test_execute_test_does_not_retry_other_option_errors(mocker, capsys):
    error_output = "traceroute: invalid option -- 'q'"
    run = mocker.patch(
        "subprocess.run",
        side_effect=_help_then(
            CompletedProcess(None, returncode=1, stdout="", stderr=error_output)
        ),
    )

    assert TraceResult.execute_test("8.8.8.8") is None
    assert run.call_count == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert error_output in captured.err


def test_execute_test_trace_timeout(mocker, capsys):
    mocker.patch(
        "subprocess.run",
        side_effect=_help_then(TimeoutExpired("traceroute", 120)),
    )

    assert TraceResult.execute_test("8.8.8.8") is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "timed out" in captured.err


def test_execute_test_missing_binary(mocker, capsys):
    run = mocker.patch("subprocess.run", side_effect=FileNotFoundError)

    x = TraceResult.execute_test("8.8.8.8")
    assert x is None
    # The probe already showed traceroute cannot run, so no trace is attempted
    # and the failure is only reported once.
    assert run.call_count == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "traceroute" in captured.err
    assert captured.err.count("ERROR:") == 1


def test_run_test_skips_failed_hops(mocker):
    trace_output = "\n".join(
        [
            "traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets",
            " 1  192.168.1.1  0.310 ms",
            " 2  10.0.0.1  1.310 ms",
            " 3  * * *",
            " 4  8.8.8.8  9.310 ms",
        ]
    )
    mocker.patch(
        "internet_troubleshooter.trace_test.TraceResult.execute_test",
        return_value=trace_output,
    )
    mocker.patch(
        "internet_troubleshooter.trace_test.PingResult.run_test",
        side_effect=[PingResult(ip="192.168.1.1", packet_loss=0.0), None],
    )

    x = TraceResult.run_test("8.8.8.8")
    assert len(x.ping_results) == 1
    assert x.ping_results[0].ip == "192.168.1.1"


def test_run_test_deduplicates_hop_ips(mocker):
    trace_output = "\n".join(
        [
            "traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets",
            " 1  192.168.1.1  0.310 ms",
            " 2  10.0.0.1  1.310 ms",
            " 3  10.0.0.1  1.420 ms",
            " 4  192.168.1.1  1.500 ms",
            " 5  * * *",
            " 6  10.0.0.1  2.100 ms",
            " 7  8.8.8.8  9.310 ms",
        ]
    )
    mocker.patch(
        "internet_troubleshooter.trace_test.TraceResult.execute_test",
        return_value=trace_output,
    )
    ping = mocker.patch(
        "internet_troubleshooter.trace_test.PingResult.run_test",
        side_effect=lambda ip, hop_count=None: PingResult(ip=ip, packet_loss=0.0),
    )

    x = TraceResult.run_test("8.8.8.8")

    assert [result.ip for result in x.ping_results] == ["192.168.1.1", "10.0.0.1"]
    assert [call.args[0] for call in ping.call_args_list] == [
        "192.168.1.1",
        "10.0.0.1",
    ]


def test_hop_ips_preserves_first_seen_order():
    trace_output = "\n".join(
        [
            " 1  10.0.0.2  0.1 ms",
            " 2  10.0.0.1  0.2 ms",
            " 3  10.0.0.2  0.3 ms",
            " 4  198.51.100.7  0.4 ms",
        ]
    )

    assert TraceResult.hop_ips(trace_output, "198.51.100.7") == [
        "10.0.0.2",
        "10.0.0.1",
    ]


def test_hop_ips_debug_logging(capsys, caplog):
    trace_output = "\n".join(
        [
            " 1  10.0.0.1  0.1 ms",
            " 2  8.8.8.8  0.2 ms",
        ]
    )

    with caplog.at_level(logging.DEBUG):
        assert TraceResult.hop_ips(trace_output, "8.8.8.8") == ["10.0.0.1"]

    assert capsys.readouterr().err == ""
    assert "trace_ip: 10.0.0.1" in caplog.text
    assert "trace_ip: 8.8.8.8" in caplog.text


def test_hop_ips_quiet_without_debug_level(caplog):
    trace_output = " 1  10.0.0.1  0.1 ms"

    with caplog.at_level(logging.INFO):
        assert TraceResult.hop_ips(trace_output, "8.8.8.8") == ["10.0.0.1"]

    assert caplog.records == []


def test_run_test_debug_logging(mocker, capsys, caplog):
    trace_output = " 1  192.168.1.1  0.310 ms\n 2  8.8.8.8  9.310 ms"
    mocker.patch(
        "internet_troubleshooter.trace_test.TraceResult.execute_test",
        return_value=trace_output,
    )
    mocker.patch(
        "internet_troubleshooter.trace_test.PingResult.run_test",
        return_value=PingResult(ip="192.168.1.1", packet_loss=0.0),
    )

    with caplog.at_level(logging.DEBUG):
        TraceResult.run_test("8.8.8.8")

    assert capsys.readouterr().err == ""
    assert "Running Traceroute" in caplog.text
    assert "Traceroute: {}".format(trace_output) in caplog.text
    assert "trace_ip: 192.168.1.1" in caplog.text


@pytest.mark.parametrize(
    "uid, expected",
    [
        (0, DEFAULT_TRACE_HOP_PING_COUNT_ROOT),
        (1000, DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT),
    ],
)
def test_default_hop_ping_count(mocker, uid, expected):
    mocker.patch("os.geteuid", return_value=uid)

    assert default_hop_ping_count() == expected


def _patch_trace_with_one_hop(mocker):
    trace_output = "\n".join(
        [
            " 1  192.168.1.1  0.310 ms",
            " 2  8.8.8.8  9.310 ms",
        ]
    )
    mocker.patch(
        "internet_troubleshooter.trace_test.TraceResult.execute_test",
        return_value=trace_output,
    )
    return mocker.patch(
        "internet_troubleshooter.trace_test.PingResult.run_test",
        return_value=PingResult(ip="192.168.1.1", packet_loss=0.0),
    )


@pytest.mark.parametrize("hop_count", [1, 10, 50, 400])
def test_run_test_uses_requested_count_for_hops(mocker, hop_count):
    ping = _patch_trace_with_one_hop(mocker)

    TraceResult.run_test("8.8.8.8", hop_count)

    assert ping.call_args.args == ("192.168.1.1", hop_count)


@pytest.mark.parametrize(
    "uid, expected",
    [
        (0, DEFAULT_TRACE_HOP_PING_COUNT_ROOT),
        (1000, DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT),
    ],
)
def test_run_test_hop_count_defaults_by_uid(mocker, uid, expected):
    ping = _patch_trace_with_one_hop(mocker)
    mocker.patch("os.geteuid", return_value=uid)

    TraceResult.run_test("8.8.8.8")

    assert ping.call_args.args == ("192.168.1.1", expected)


def test_run_test_no_trace(mocker):
    mocker.patch(
        "internet_troubleshooter.trace_test.TraceResult.execute_test",
        return_value=None,
    )

    assert TraceResult.run_test("8.8.8.8") is None


def test_execute_test_error(mocker, capsys):
    test_output = """TEST STRING"""
    error_output = """ERROR STRING"""

    mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            None, returncode=1, stdout=test_output, stderr=error_output
        ),
    )

    x = TraceResult.execute_test("8.8.8.8")
    assert x is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert error_output in captured.err
