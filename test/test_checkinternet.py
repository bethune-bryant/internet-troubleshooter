import logging
from argparse import Namespace

import pytest

from internet_troubleshooter import checkinternet
from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.result import TestResult as InternetTestResult
from internet_troubleshooter.speed_test import SpeedResult
from internet_troubleshooter.trace_test import (
    DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT,
    DEFAULT_TRACE_HOP_PING_COUNT_ROOT,
)


def make_args(**overrides):
    args = {
        "debug": False,
        "ping_ip": "8.8.8.8",
        "ping_count": 1,
        "trace_hop_ping_count": None,
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
    trace = run_with_ping(mocker, PingResult(ip="8.8.8.8", packet_loss=50.0))
    capsys.readouterr()
    assert trace.called


def test_run_skips_trace_when_healthy(mocker, capsys):
    trace = run_with_ping(mocker, PingResult(ip="8.8.8.8", packet_loss=0.0))
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


@pytest.mark.parametrize("trace_hop_ping_count", [0, -1, -50])
def test_run_rejects_invalid_trace_hop_ping_count(mocker, capsys, trace_hop_ping_count):
    ping = mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=None,
    )

    args = make_args(trace_hop_ping_count=trace_hop_ping_count)
    assert checkinternet.run(args) == 1

    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "--trace_hop_ping_count" in captured.err
    assert not ping.called


@pytest.mark.parametrize(
    "uid, expected",
    [
        (0, DEFAULT_TRACE_HOP_PING_COUNT_ROOT),
        (1000, DEFAULT_TRACE_HOP_PING_COUNT_NON_ROOT),
    ],
)
def test_run_trace_hop_count_defaults_by_uid(mocker, capsys, uid, expected):
    mocker.patch("os.geteuid", return_value=uid)
    trace = run_with_ping(
        mocker,
        PingResult(ip="8.8.8.8", packet_loss=50.0),
        ping_count=400,
        trace_hop_ping_count=None,
    )
    capsys.readouterr()

    assert trace.call_args.args == ("8.8.8.8", expected)


def test_run_trace_hop_count_uses_explicit_value(mocker, capsys):
    mocker.patch("os.geteuid", return_value=0)
    trace = run_with_ping(
        mocker,
        PingResult(ip="8.8.8.8", packet_loss=50.0),
        ping_count=400,
        trace_hop_ping_count=7,
    )
    capsys.readouterr()

    assert trace.call_args.args == ("8.8.8.8", 7)


def test_run_pings_hops_with_hop_count_not_ping_count(mocker, capsys):
    trace_output = "\n".join(
        [
            " 1  192.168.1.1  0.310 ms",
            " 2  10.0.0.1  1.310 ms",
            " 3  8.8.8.8  9.310 ms",
        ]
    )
    mocker.patch(
        "internet_troubleshooter.trace_test.TraceResult.execute_test",
        return_value=trace_output,
    )
    ping = mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        side_effect=lambda ip, count=None: PingResult(
            ip=ip, packet_loss=50.0 if ip == "8.8.8.8" else 0.0
        ),
    )

    args = make_args(ping_count=400, trace_hop_ping_count=25)
    assert checkinternet.run(args) == 0
    capsys.readouterr()

    assert [call.args for call in ping.call_args_list] == [
        ("8.8.8.8", 400),
        ("192.168.1.1", 25),
        ("10.0.0.1", 25),
    ]


def test_run_accepts_unset_ping_count(mocker, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packet_loss=0.0),
    )

    assert checkinternet.run(make_args(ping_count=None)) == 0
    capsys.readouterr()


def test_run_succeeds_when_ping_works(mocker, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packet_loss=0.0),
    )

    assert checkinternet.run(make_args()) == 0
    assert "Packet Loss: 0.00%" in capsys.readouterr().out


def test_run_debug_logging_ping_only(mocker, capsys, caplog):
    ping_result = PingResult(ip="8.8.8.8", packet_loss=0.0)
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=ping_result,
    )
    trace = mocker.patch(
        "internet_troubleshooter.checkinternet.TraceResult.run_test",
        return_value=None,
    )

    with caplog.at_level(logging.DEBUG):
        assert checkinternet.run(make_args()) == 0
    assert not trace.called

    assert "Packet Loss: 0.00%" in capsys.readouterr().out
    assert "Running Tests" in caplog.text
    assert "Running PingTest" in caplog.text
    assert "Ping Result: {}".format(ping_result) in caplog.text
    assert "Running TraceTest" not in caplog.text
    assert "Running SpeedTest" not in caplog.text


def test_run_debug_logging_with_trace_and_yaml(mocker, tmp_path, capsys, caplog):
    yaml_file = tmp_path / "results.yaml"
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=None,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.TraceResult.run_test",
        return_value=None,
    )

    with caplog.at_level(logging.DEBUG):
        assert (
            checkinternet.run(make_args(yaml_file=str(yaml_file), skip_speedtest=True))
            == 1
        )

    assert capsys.readouterr().out == ""
    assert "Running TraceTest" in caplog.text
    assert "Logging results to: {}".format(yaml_file) in caplog.text


def test_run_debug_logging_with_speedtest(mocker, capsys, caplog):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packet_loss=0.0),
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.check",
        return_value=True,
    )
    mocker.patch(
        "internet_troubleshooter.checkinternet.SpeedResult.run_test",
        return_value=SpeedResult(upload=1.0, download=2.0, latency=3.0),
    )

    with caplog.at_level(logging.DEBUG):
        assert checkinternet.run(make_args(skip_speedtest=False)) == 0

    captured = capsys.readouterr()
    assert "Packet Loss: 0.00%" in captured.out
    assert "Download:" in captured.out
    assert "Running SpeedTest" in caplog.text


def test_run_debug_logging_records_only_debug_level(mocker, capsys, caplog):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packet_loss=0.0),
    )

    with caplog.at_level(logging.DEBUG):
        assert checkinternet.run(make_args()) == 0

    capsys.readouterr()
    assert caplog.records
    assert all(record.levelno == logging.DEBUG for record in caplog.records)


def test_main_configures_logging_from_debug_flag(mocker):
    mocker.patch("sys.argv", ["checkinternet", "--debug", "run", "--skip_pingtest"])
    configure = mocker.patch("internet_troubleshooter.checkinternet.configure_logging")
    mocker.patch("internet_troubleshooter.checkinternet.run", return_value=0)

    with pytest.raises(SystemExit):
        checkinternet.main()

    assert configure.call_args.args == (True,)


def test_main_configures_logging_without_debug_flag(mocker):
    mocker.patch("sys.argv", ["checkinternet", "run", "--skip_pingtest"])
    configure = mocker.patch("internet_troubleshooter.checkinternet.configure_logging")
    mocker.patch("internet_troubleshooter.checkinternet.run", return_value=0)

    with pytest.raises(SystemExit):
        checkinternet.main()

    assert configure.call_args.args == (False,)


def test_main_debug_logs_parsed_args(mocker, capsys, caplog):
    mocker.patch("sys.argv", ["checkinternet", "--debug", "run", "--skip_pingtest"])
    mocker.patch("internet_troubleshooter.checkinternet.configure_logging")
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=None,
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(SystemExit) as excinfo:
            checkinternet.main()
    assert excinfo.value.code == 0

    capsys.readouterr()
    assert "Parsed Args: " in caplog.text
    assert "skip_pingtest=True" in caplog.text


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
        return_value=PingResult(ip="8.8.8.8", packet_loss=2.0),
    )

    assert checkinternet.run(make_args(yaml_file=str(yaml_file))) == 0
    assert checkinternet.run(make_args(yaml_file=str(yaml_file))) == 0
    capsys.readouterr()

    text = yaml_file.read_text(encoding="utf-8")
    assert "!!python/object" not in text

    results = InternetTestResult.load_results(str(yaml_file))
    assert len(results) == 2
    assert all(result.ping_result.packet_loss == 2.0 for result in results)


def test_run_reports_unwritable_yaml_file(mocker, tmp_path, capsys):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="8.8.8.8", packet_loss=0.0),
    )

    args = make_args(yaml_file=str(tmp_path / "missing" / "results.yaml"))
    assert checkinternet.run(args) == 1

    captured = capsys.readouterr()
    assert "ERROR: Unable to write results" in captured.err


def test_display_human(tmp_path, capsys):
    yaml_file = tmp_path / "results.yaml"
    with open(yaml_file, "a", encoding="utf-8") as f:
        for packet_loss in (10.0, 20.0):
            result = InternetTestResult(
                ping_result=PingResult(ip="8.8.8.8", packet_loss=packet_loss),
                trace_result=None,
                speed_result=None,
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
        ping_result=PingResult(ip="8.8.8.8", packet_loss=1.0),
        trace_result=None,
        speed_result=None,
    )
    yaml_file.write_text("---\n{}\n...\n".format(result.to_yaml()), encoding="utf-8")

    to_html = mocker.patch("internet_troubleshooter.checkinternet.TestResult.to_html")

    args = Namespace(yaml_file=str(yaml_file), format="html")
    assert checkinternet.display(args) == 0

    assert to_html.call_args.args[0][0].ping_result.packet_loss == 1.0
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
            "--trace_hop_ping_count",
            "4",
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
    assert args.trace_hop_ping_count == 4
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
