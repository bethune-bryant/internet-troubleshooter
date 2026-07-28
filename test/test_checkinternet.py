from argparse import Namespace

import pytest

from internet_troubleshooter import checkinternet
from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.result import TestResult as InternetTestResult
from internet_troubleshooter.speed_test import SpeedResult


def make_args(**overrides):
    args = {
        "debug": False,
        "ping_ip": "8.8.8.8",
        "ping_count": 1,
        "max_packet_loss": 3.0,
        "skip_speedtest": True,
        "skip_pingtest": False,
        "yaml_file": None,
    }
    args.update(overrides)
    return Namespace(**args)


def run_with_ping(mocker, ping_result, **overrides):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=ping_result,
    )
    trace = mocker.patch(
        "internet_troubleshooter.checkinternet.TraceResult.run_test",
        return_value=None,
    )
    checkinternet.run(make_args(**overrides))
    return trace


def test_run_traces_when_ping_fails(mocker, capsys):
    trace = run_with_ping(mocker, None)
    capsys.readouterr()
    assert trace.called


def test_run_traces_when_packet_loss_high(mocker, capsys):
    trace = run_with_ping(mocker, PingResult(ip="8.8.8.8", packetLoss=50.0))
    capsys.readouterr()
    assert trace.called


def test_run_skips_trace_when_healthy(mocker, capsys):
    trace = run_with_ping(mocker, PingResult(ip="8.8.8.8", packetLoss=0.0))
    capsys.readouterr()
    assert not trace.called


@pytest.mark.parametrize("ping_ip", ["-f", "--flood", "8.8.8.8 -f", ""])
def test_run_rejects_invalid_ping_ip(mocker, capsys, ping_ip):
    ping = mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=None,
    )

    assert checkinternet.run(make_args(ping_ip=ping_ip)) == 1

    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "--ping_ip" in captured.err
    assert not ping.called


@pytest.mark.parametrize("ping_count", [0, -1, -400])
def test_run_rejects_invalid_ping_count(mocker, capsys, ping_count):
    ping = mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=None,
    )

    assert checkinternet.run(make_args(ping_count=ping_count)) == 1

    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "--ping_count" in captured.err
    assert not ping.called


def test_run_accepts_unset_ping_count(mocker, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packetLoss=0.0),
    )

    assert checkinternet.run(make_args(ping_count=None)) == 0
    capsys.readouterr()


def test_run_succeeds_when_ping_works(mocker, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packetLoss=0.0),
    )

    assert checkinternet.run(make_args()) == 0
    assert "Packet Loss: 0.00%" in capsys.readouterr().out


def test_run_debug_logging_ping_only(mocker, capsys):
    ping_result = PingResult(ip="8.8.8.8", packetLoss=0.0)
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=ping_result,
    )
    trace = mocker.patch(
        "internet_troubleshooter.checkinternet.TraceResult.run_test",
        return_value=None,
    )

    assert checkinternet.run(make_args(debug=True)) == 0
    assert not trace.called

    captured = capsys.readouterr()
    assert "Packet Loss: 0.00%" in captured.out
    assert "Running Tests" in captured.err
    assert "Running PingTest" in captured.err
    assert "Ping Result: " in captured.err
    assert str(ping_result) in captured.err
    assert "Running TraceTest" not in captured.err
    assert "Running SpeedTest" not in captured.err


def test_run_debug_logging_with_trace_and_yaml(mocker, tmp_path, capsys):
    yaml_file = tmp_path / "results.yaml"
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=None,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.TraceResult.run_test",
        return_value=None,
    )

    assert checkinternet.run(
        make_args(debug=True, yaml_file=str(yaml_file), skip_speedtest=True)
    ) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Running TraceTest" in captured.err
    assert "Logging results to: " in captured.err
    assert str(yaml_file) in captured.err


def test_run_debug_logging_with_speedtest(mocker, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packetLoss=0.0),
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.check",
        return_value=True,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.run_test",
        return_value=SpeedResult(upload=1.0, download=2.0, latency=3.0),
    )

    assert checkinternet.run(make_args(debug=True, skip_speedtest=False)) == 0

    captured = capsys.readouterr()
    assert "Packet Loss: 0.00%" in captured.out
    assert "Download:" in captured.out
    assert "Running SpeedTest" in captured.err


def test_main_debug_logs_parsed_args(mocker, capsys):
    mocker.patch("sys.argv", ["checkinternet", "--debug", "run", "--skip_pingtest"])
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=None,
    )

    with pytest.raises(SystemExit) as excinfo:
        checkinternet.main()
    assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "Parsed Args: " in captured.err
    assert "skip_pingtest=True" in captured.err


def test_run_fails_when_every_test_fails(mocker, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=None,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.TraceResult.run_test",
        return_value=None,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.check",
        return_value=True,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.run_test",
        return_value=None,
    )

    assert checkinternet.run(make_args(skip_speedtest=False)) == 1
    assert "ERROR: All requested tests failed." in capsys.readouterr().err


def test_run_succeeds_when_one_test_works(mocker, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=None,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.TraceResult.run_test",
        return_value=None,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.check",
        return_value=True,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.run_test",
        return_value=SpeedResult(upload=1.0, download=2.0, latency=3.0),
    )

    assert checkinternet.run(make_args(skip_speedtest=False)) == 0
    capsys.readouterr()


def test_run_succeeds_when_all_tests_skipped(capsys):
    args = make_args(skip_pingtest=True, skip_speedtest=True)
    assert checkinternet.run(args) == 0
    capsys.readouterr()


def test_run_succeeds_when_speedtest_unavailable(mocker, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.check",
        return_value=False,
    )
    speed = mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.run_test",
        return_value=None,
    )

    args = make_args(skip_pingtest=True, skip_speedtest=False)
    assert checkinternet.run(args) == 0
    assert not speed.called
    capsys.readouterr()


def test_run_writes_yaml_file(mocker, tmp_path, capsys):
    yaml_file = tmp_path / "results.yaml"
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packetLoss=2.0),
    )

    assert checkinternet.run(make_args(yaml_file=str(yaml_file))) == 0
    assert checkinternet.run(make_args(yaml_file=str(yaml_file))) == 0
    capsys.readouterr()

    text = yaml_file.read_text(encoding="utf-8")
    assert "!!python/object" not in text

    results = InternetTestResult.load_results(str(yaml_file))
    assert len(results) == 2
    assert all(result.pingResult.packetLoss == 2.0 for result in results)


def test_run_reports_unwritable_yaml_file(mocker, tmp_path, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packetLoss=0.0),
    )

    args = make_args(yaml_file=str(tmp_path / "missing" / "results.yaml"))
    assert checkinternet.run(args) == 1

    captured = capsys.readouterr()
    assert "ERROR: Unable to write results" in captured.err


def test_display_human(tmp_path, capsys):
    yaml_file = tmp_path / "results.yaml"
    with open(yaml_file, "a", encoding="utf-8") as f:
        for packetLoss in (10.0, 20.0):
            result = InternetTestResult(
                pingResult=PingResult(ip="8.8.8.8", packetLoss=packetLoss),
                traceResult=None,
                speedResult=None,
            )
            print("---\n{}\n...\n".format(result.to_yaml()), file=f)

    args = Namespace(yaml_file=str(yaml_file), format="human")
    assert checkinternet.display(args) == 0

    captured = capsys.readouterr()
    assert "Mean: 15.00%" in captured.out
    assert "Latency: Not enough data." in captured.out


def test_display_html(mocker, tmp_path, capsys):
    yaml_file = tmp_path / "results.yaml"
    result = InternetTestResult(
        pingResult=PingResult(ip="8.8.8.8", packetLoss=1.0),
        traceResult=None,
        speedResult=None,
    )
    yaml_file.write_text("---\n{}\n...\n".format(result.to_yaml()), encoding="utf-8")

    to_html = mocker.patch("internet_troubleshooter.checkinternet.TestResult.to_html")

    args = Namespace(yaml_file=str(yaml_file), format="html")
    assert checkinternet.display(args) == 0

    assert to_html.call_args.args[0][0].pingResult.packetLoss == 1.0
    capsys.readouterr()


def test_display_reports_missing_file(tmp_path, capsys):
    args = Namespace(yaml_file=str(tmp_path / "missing.yaml"), format="human")
    assert checkinternet.display(args) == 1
    assert "ERROR: Unable to read results" in capsys.readouterr().err


def test_cli_input_run(mocker):
    mocker.patch(
        "sys.argv",
        [
            "checkinternet",
            "--debug",
            "run",
            "--ping_ip",
            "1.1.1.1",
            "--ping_count",
            "5",
            "--max_packet_loss",
            "10",
            "--skip_speedtest",
            "--yaml_file",
            "out.yaml",
        ],
    )

    args = checkinternet.cli_input()
    assert args.debug
    assert args.command == "run"
    assert args.ping_ip == "1.1.1.1"
    assert args.ping_count == 5
    assert args.max_packet_loss == 10.0
    assert args.skip_speedtest
    assert not args.skip_pingtest
    assert args.yaml_file == "out.yaml"
    assert args.func is checkinternet.run


def test_cli_input_display_defaults(mocker):
    mocker.patch("sys.argv", ["checkinternet", "display", "--yaml_file", "in.yaml"])

    args = checkinternet.cli_input()
    assert args.command == "display"
    assert args.format == "human"
    assert args.func is checkinternet.display


def test_cli_input_requires_command(mocker, capsys):
    mocker.patch("sys.argv", ["checkinternet"])

    with pytest.raises(SystemExit) as excinfo:
        checkinternet.cli_input()
    assert excinfo.value.code == 2
    capsys.readouterr()


def test_main_exits_with_command_status(mocker):
    mocker.patch("sys.argv", ["checkinternet", "display", "--yaml_file", "in.yaml"])
    mocker.patch(
        "internet_troubleshooter.checkinternet.display",
        return_value=3,
    )

    with pytest.raises(SystemExit) as excinfo:
        checkinternet.main()
    assert excinfo.value.code == 3
