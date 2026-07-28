from subprocess import CompletedProcess

import pytest

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult, parse_trace_line


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
