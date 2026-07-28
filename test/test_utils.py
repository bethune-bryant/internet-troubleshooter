import subprocess
from subprocess import CompletedProcess

from internet_troubleshooter.utils import debug, run_command, safe_mean, summarize


def test_debug(capsys):
    debug(False, "TEST1")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    debug(True, "TEST2")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "TEST2\n"


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
