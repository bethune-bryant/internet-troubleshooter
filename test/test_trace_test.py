from subprocess import CompletedProcess

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult


def test_TraceResult():
    x = TraceResult([PingResult(ip="1.1.1.1", packetLoss=10)])
    assert x.pingResults[0].ip == "1.1.1.1"
    assert x.pingResults[0].packetLoss == 10


def test_execute_test(mocker, capsys):
    test_output = """TEST STRING"""

    mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(None, returncode=0, stdout=test_output),
    )

    x = TraceResult.execute_test("8.8.8.8")
    assert test_output == x
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


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
