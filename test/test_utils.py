import subprocess
from subprocess import CompletedProcess

import pytest

from internet_troubleshooter.utils import (
    debug,
    is_valid_host,
    run_command,
    safe_mean,
    summarize,
)


def test_debug_disabled(capsys):
    debug(False, "TEST1")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_debug_writes_to_stderr(capsys):
    debug(True, "TEST2")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "TEST2\n"


def test_debug_multiple_args(capsys):
    debug(True, "Ping Result: ", "10.00%: 8.8.8.8")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Ping Result:  10.00%: 8.8.8.8\n"


def test_debug_kwargs(capsys):
    debug(True, "line1", "line2", sep="|", end="")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "line1|line2"


def test_summarize():
    x = summarize([1.0, 2.0, 3.0], title="Test")
    assert "Mean: 2.00" in x
    assert "Variance: 1.00" in x
    assert "Min: 1.00" in x
    assert "Max: 3.00" in x


def test_summarize_error():
    x = summarize([], title="Test")
    assert x == "Test: Not enough data."
    x = summarize([1.0], title="Test")
    assert x == "Test: Not enough data."


def test_safe_mean():
    assert safe_mean([1.0, 2.0, 3.0]) == 2.0
    assert safe_mean([]) is None


@pytest.mark.parametrize(
    "host",
    [
        "8.8.8.8",
        "127.0.0.1",
        "2001:4860:4860::8888",
        "::1",
        "example.com",
        "my-router.local",
        "example.com.",
        "a",
    ],
)
def test_is_valid_host_accepts(host):
    assert is_valid_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "-f",
        "--flood",
        "-8.8.8.8",
        "8.8.8.8 -f",
        "8.8.8.8;rm -rf /",
        "example..com",
        "example-.com",
        "",
        None,
        "a" * 254,
        ".",
    ],
)
def test_is_valid_host_rejects(host):
    assert not is_valid_host(host)


def test_run_command(mocker, capsys):
    expected = CompletedProcess(None, returncode=0, stdout="OUTPUT")
    run = mocker.patch("subprocess.run", return_value=expected)

    x = run_command(["mycommand", "-h"], timeout=7)
    assert x is expected
    assert run.call_args.args[0] == ["mycommand", "-h"]
    assert run.call_args.kwargs["capture_output"]
    assert run.call_args.kwargs["text"]
    assert run.call_args.kwargs["timeout"] == 7
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_run_command_missing_binary(mocker, capsys):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)

    x = run_command(["mycommand"])
    assert x is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "mycommand" in captured.err


def test_run_command_timeout(mocker, capsys):
    mocker.patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="mycommand", timeout=5),
    )

    x = run_command(["mycommand"], timeout=5)
    assert x is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "timed out" in captured.err


def test_run_command_os_error(mocker, capsys):
    mocker.patch("subprocess.run", side_effect=PermissionError("denied"))

    x = run_command(["mycommand"])
    assert x is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "denied" in captured.err
