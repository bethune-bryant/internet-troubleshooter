import logging
from subprocess import CompletedProcess

import pytest

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import (
    DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT,
    DEFAULT_TRACE_HOP_PING_COUNT_ROOT,
    TraceResult,
    default_hop_ping_count,
    parse_trace_line,
)


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
    x = TraceResult([PingResult(ip="1.1.1.1", packetLoss=10)])
    assert x.pingResults[0].ip == "1.1.1.1"
    assert x.pingResults[0].packetLoss == 10


def test_execute_test(mocker, capsys):
    test_output = """TEST STRING"""

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


def test_execute_test_missing_binary(mocker, capsys):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)

    x = TraceResult.execute_test("8.8.8.8")
    assert x is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "traceroute" in captured.err


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
        side_effect=[PingResult(ip="192.168.1.1", packetLoss=0.0), None],
    )

    x = TraceResult.run_test("8.8.8.8")
    assert len(x.pingResults) == 1
    assert x.pingResults[0].ip == "192.168.1.1"


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
        side_effect=lambda ip, hop_count=None: PingResult(ip=ip, packetLoss=0.0),
    )

    x = TraceResult.run_test("8.8.8.8")

    assert [result.ip for result in x.pingResults] == ["192.168.1.1", "10.0.0.1"]
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
        return_value=PingResult(ip="192.168.1.1", packetLoss=0.0),
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
        return_value=PingResult(ip="192.168.1.1", packetLoss=0.0),
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
