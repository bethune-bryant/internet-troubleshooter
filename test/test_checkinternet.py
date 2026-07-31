import io
import logging
from argparse import Namespace

import pytest

from internet_troubleshooter import __version__, checkinternet
from internet_troubleshooter.config import default_config_path
from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.render import RenderThresholds
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

    to_html = mocker.patch("internet_troubleshooter.checkinternet.to_html")

    args = Namespace(
        yaml_file=str(yaml_file),
        format="html",
        embed_plotly=False,
        target_download_mbps=100.0,
        target_upload_mbps=50.0,
        target_latency_ms=10.0,
        target_packet_loss_pct=1.5,
    )
    assert checkinternet.display(args) == 0

    assert to_html.call_args.args[0][0].ping_result.packet_loss == 1.0
    assert to_html.call_args.args[2] == RenderThresholds(
        download_mbps=100.0,
        upload_mbps=50.0,
        latency_ms=10.0,
        packet_loss_pct=1.5,
    )
    assert to_html.call_args.kwargs["embed_plotly"] is False
    capsys.readouterr()


def test_display_html_embeds_plotly_when_asked(mocker, tmp_path, capsys):
    yaml_file = tmp_path / "results.yaml"
    result = InternetTestResult(
        ping_result=PingResult(ip="8.8.8.8", packet_loss=1.0),
        trace_result=None,
        speed_result=None,
    )
    yaml_file.write_text("---\n{}\n...\n".format(result.to_yaml()), encoding="utf-8")

    to_html = mocker.patch("internet_troubleshooter.checkinternet.to_html")

    args = Namespace(
        yaml_file=str(yaml_file),
        format="html",
        embed_plotly=True,
        target_download_mbps=50.0,
        target_upload_mbps=15.0,
        target_latency_ms=20.0,
        target_packet_loss_pct=3.0,
    )
    assert checkinternet.display(args) == 0

    assert to_html.call_args.kwargs["embed_plotly"] is True
    capsys.readouterr()


def test_display_reports_missing_file(tmp_path, capsys):
    args = Namespace(yaml_file=str(tmp_path / "missing.yaml"), format="human")
    assert checkinternet.display(args) == 1
    assert "ERROR: Unable to read results" in capsys.readouterr().err


def results_yaml(*packet_losses):
    documents = []
    for packet_loss in packet_losses:
        result = InternetTestResult(
            ping_result=PingResult(ip="8.8.8.8", packet_loss=packet_loss),
            trace_result=None,
            speed_result=None,
        )
        documents.append("---\n{}\n...\n".format(result.to_yaml()))
    return "".join(documents)


def test_display_human_from_stdin(mocker, capsys):
    mocker.patch("sys.stdin", io.StringIO(results_yaml(10.0, 20.0)))

    args = Namespace(yaml_file="-", format="human")
    assert checkinternet.display(args) == 0

    captured = capsys.readouterr()
    assert "Mean: 15.00%" in captured.out
    assert "Latency: Not enough data." in captured.out


def test_display_html_from_stdin(mocker, capsys):
    mocker.patch("sys.stdin", io.StringIO(results_yaml(1.0)))
    to_html = mocker.patch("internet_troubleshooter.checkinternet.to_html")

    args = Namespace(
        yaml_file="-",
        format="html",
        embed_plotly=False,
        target_download_mbps=50.0,
        target_upload_mbps=15.0,
        target_latency_ms=20.0,
        target_packet_loss_pct=3.0,
    )
    assert checkinternet.display(args) == 0

    assert to_html.call_args.args[0][0].ping_result.packet_loss == 1.0
    capsys.readouterr()


@pytest.mark.parametrize("content", ["", "   \n\t\n"])
def test_display_reports_empty_stdin(mocker, capsys, content):
    mocker.patch("sys.stdin", io.StringIO(content))

    args = Namespace(yaml_file="-", format="human")
    assert checkinternet.display(args) == 1

    captured = capsys.readouterr()
    assert "ERROR: No results on stdin" in captured.err
    assert captured.out == ""


def test_display_does_not_read_stdin_for_a_file(mocker, tmp_path, capsys):
    yaml_file = tmp_path / "results.yaml"
    yaml_file.write_text(results_yaml(10.0, 20.0), encoding="utf-8")
    piped = results_yaml(90.0)
    stdin = mocker.patch("sys.stdin", io.StringIO(piped))

    args = Namespace(yaml_file=str(yaml_file), format="human")
    assert checkinternet.display(args) == 0

    assert "Mean: 15.00%" in capsys.readouterr().out
    assert stdin.read() == piped


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
    assert args.embed_plotly is False
    assert args.target_download_mbps == 50
    assert args.target_upload_mbps == 15
    assert args.target_latency_ms == 20
    assert args.target_packet_loss_pct == 3
    assert args.func is checkinternet.display


def test_cli_input_display_accepts_stdin_sentinel(mocker):
    mocker.patch("sys.argv", ["checkinternet", "display", "--yaml_file", "-"])

    args = checkinternet.cli_input()
    assert args.yaml_file == "-"
    assert args.func is checkinternet.display


def test_cli_input_display_accepts_custom_thresholds(mocker):
    mocker.patch(
        "sys.argv",
        [
            "checkinternet",
            "display",
            "--yaml_file",
            "in.yaml",
            "--format",
            "html",
            "--target_download_mbps",
            "200",
            "--target_upload_mbps",
            "100",
            "--target_latency_ms",
            "12.5",
            "--target_packet_loss_pct",
            "0.5",
        ],
    )

    args = checkinternet.cli_input()
    assert args.format == "html"
    assert checkinternet._display_thresholds(args) == RenderThresholds(
        download_mbps=200.0,
        upload_mbps=100.0,
        latency_ms=12.5,
        packet_loss_pct=0.5,
    )


def test_cli_input_display_accepts_embed_plotly(mocker):
    mocker.patch(
        "sys.argv",
        [
            "checkinternet",
            "display",
            "--yaml_file",
            "in.yaml",
            "--format",
            "html",
            "--embed_plotly",
        ],
    )

    args = checkinternet.cli_input()
    assert args.embed_plotly is True


def test_cli_input_requires_command(mocker, capsys):
    mocker.patch("sys.argv", ["checkinternet"])

    with pytest.raises(SystemExit) as excinfo:
        checkinternet.cli_input()
    assert excinfo.value.code == 2
    capsys.readouterr()


def test_cli_input_version_without_command(mocker, capsys):
    mocker.patch("sys.argv", ["checkinternet", "--version"])

    with pytest.raises(SystemExit) as excinfo:
        checkinternet.cli_input()
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == "checkinternet {}".format(__version__)


def write_config(tmp_path, content, name="config.yaml"):
    config_file = tmp_path / name
    config_file.write_text(content, encoding="utf-8")
    return str(config_file)


def cli_input_with_config(mocker, config_path, *argv):
    command_line = ["checkinternet"]
    if config_path is not None:
        command_line += ["--config", config_path]
    mocker.patch("sys.argv", command_line + list(argv))
    return checkinternet.cli_input()


def test_cli_input_run_takes_defaults_from_config(mocker, tmp_path):
    config_path = write_config(
        tmp_path,
        "run:\n"
        "  ping_ip: 1.1.1.1\n"
        "  ping_count: 25\n"
        "  trace_hop_ping_count: 7\n"
        "  max_packet_loss: 2.0\n"
        "  yaml_file: /var/log/results.yaml\n",
    )

    args = cli_input_with_config(mocker, config_path, "run")
    assert args.ping_ip == "1.1.1.1"
    assert args.ping_count == 25
    assert args.trace_hop_ping_count == 7
    assert args.max_packet_loss == 2.0
    assert args.yaml_file == "/var/log/results.yaml"
    assert args.skip_speedtest is False
    assert args.func is checkinternet.run


def test_cli_input_run_flags_override_config(mocker, tmp_path):
    config_path = write_config(
        tmp_path,
        "run:\n  ping_ip: 1.1.1.1\n  ping_count: 25\n  yaml_file: /var/log/from.yaml\n",
    )

    args = cli_input_with_config(
        mocker,
        config_path,
        "run",
        "--ping_ip",
        "9.9.9.9",
        "--yaml_file",
        "cli.yaml",
    )
    assert args.ping_ip == "9.9.9.9"
    assert args.yaml_file == "cli.yaml"
    assert args.ping_count == 25


def test_cli_input_flag_matching_the_builtin_default_overrides_config(mocker, tmp_path):
    config_path = write_config(
        tmp_path, "run:\n  ping_ip: 1.1.1.1\n  max_packet_loss: 2.0\n"
    )

    args = cli_input_with_config(
        mocker,
        config_path,
        "run",
        "--ping_ip",
        "8.8.8.8",
        "--max_packet_loss",
        "3.0",
    )
    assert args.ping_ip == "8.8.8.8"
    assert args.max_packet_loss == 3.0


def test_cli_input_run_skip_flags_from_config(mocker, tmp_path):
    config_path = write_config(
        tmp_path, "run:\n  skip_speedtest: true\n  skip_pingtest: true\n"
    )

    args = cli_input_with_config(mocker, config_path, "run")
    assert args.skip_speedtest is True
    assert args.skip_pingtest is True


def test_cli_input_skip_flag_overrides_config_turning_it_off(mocker, tmp_path):
    config_path = write_config(tmp_path, "run:\n  skip_speedtest: false\n")

    args = cli_input_with_config(mocker, config_path, "run", "--skip_speedtest")
    assert args.skip_speedtest is True


def test_cli_input_display_takes_defaults_from_config(mocker, tmp_path):
    config_path = write_config(
        tmp_path,
        "display:\n"
        "  yaml_file: /var/log/results.yaml\n"
        "  format: html\n"
        "  embed_plotly: true\n"
        "  target_download_mbps: 500\n"
        "  target_upload_mbps: 100\n"
        "  target_latency_ms: 15\n"
        "  target_packet_loss_pct: 0.5\n",
    )

    args = cli_input_with_config(mocker, config_path, "display")
    assert args.yaml_file == "/var/log/results.yaml"
    assert args.format == "html"
    assert args.embed_plotly is True
    assert checkinternet._display_thresholds(args) == RenderThresholds(
        download_mbps=500.0,
        upload_mbps=100.0,
        latency_ms=15.0,
        packet_loss_pct=0.5,
    )
    assert args.func is checkinternet.display


def test_cli_input_display_flags_override_config(mocker, tmp_path):
    config_path = write_config(
        tmp_path,
        "display:\n"
        "  yaml_file: /var/log/results.yaml\n"
        "  format: html\n"
        "  target_download_mbps: 500\n",
    )

    args = cli_input_with_config(
        mocker,
        config_path,
        "display",
        "--yaml_file",
        "-",
        "--format",
        "human",
    )
    assert args.yaml_file == "-"
    assert args.format == "human"
    assert args.target_download_mbps == 500.0


def test_cli_input_display_embed_plotly_from_config(mocker, tmp_path):
    config_path = write_config(
        tmp_path, "display:\n  yaml_file: results.yaml\n  embed_plotly: true\n"
    )

    args = cli_input_with_config(mocker, config_path, "display")
    assert args.embed_plotly is True


def test_cli_input_reads_the_default_config_file(mocker):
    config_path = default_config_path()
    config_path.parent.mkdir(parents=True)
    config_path.write_text("run:\n  ping_ip: 1.1.1.1\n", encoding="utf-8")

    args = cli_input_with_config(mocker, None, "run")
    assert args.ping_ip == "1.1.1.1"


def test_cli_input_without_a_config_file_uses_builtin_defaults(mocker):
    args = cli_input_with_config(mocker, None, "run")
    assert args.ping_ip == "8.8.8.8"
    assert args.ping_count is None
    assert args.max_packet_loss == 3.0
    assert args.skip_speedtest is False
    assert args.yaml_file is None


def test_cli_input_ignores_the_section_of_another_command(mocker, tmp_path):
    config_path = write_config(
        tmp_path, "display:\n  yaml_file: results.yaml\n  format: html\n"
    )

    args = cli_input_with_config(mocker, config_path, "run")
    assert args.ping_ip == "8.8.8.8"
    assert args.yaml_file is None


def test_cli_input_reports_invalid_config(mocker, tmp_path, capsys):
    config_path = write_config(tmp_path, "run:\n  ping_ip: [1, 2\n")

    with pytest.raises(SystemExit) as excinfo:
        cli_input_with_config(mocker, config_path, "run")
    assert excinfo.value.code == 2

    captured = capsys.readouterr()
    assert "ERROR: Unable to parse config file" in captured.err
    assert captured.out == ""


def test_cli_input_reports_an_unknown_config_option(mocker, tmp_path, capsys):
    config_path = write_config(tmp_path, "run:\n  ping_ipp: 1.1.1.1\n")

    with pytest.raises(SystemExit) as excinfo:
        cli_input_with_config(mocker, config_path, "run")
    assert excinfo.value.code == 2
    assert "ERROR: Config file" in capsys.readouterr().err


def test_cli_input_reports_a_missing_named_config_file(mocker, tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli_input_with_config(mocker, str(tmp_path / "missing.yaml"), "run")
    assert excinfo.value.code == 2
    assert "does not exist" in capsys.readouterr().err


def test_cli_input_display_requires_a_yaml_file_from_somewhere(
    mocker, tmp_path, capsys
):
    config_path = write_config(tmp_path, "display:\n  format: html\n")

    with pytest.raises(SystemExit) as excinfo:
        cli_input_with_config(mocker, config_path, "display")
    assert excinfo.value.code == 2

    captured = capsys.readouterr()
    assert "ERROR: display requires --yaml_file" in captured.err
    assert captured.out == ""


def test_main_uses_config_defaults(mocker, tmp_path, capsys):
    yaml_file = tmp_path / "results.yaml"
    config_path = write_config(
        tmp_path,
        "run:\n  ping_ip: 1.1.1.1\n  skip_speedtest: true\n  yaml_file: {}\n".format(
            yaml_file
        ),
    )
    ping = mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=PingResult(ip="1.1.1.1", packet_loss=0.0),
    )
    mocker.patch("sys.argv", ["checkinternet", "--config", config_path, "run"])

    with pytest.raises(SystemExit) as excinfo:
        checkinternet.main()
    assert excinfo.value.code == 0

    capsys.readouterr()
    assert ping.call_args.args[0] == "1.1.1.1"
    assert yaml_file.is_file()


def test_main_exits_with_command_status(mocker):
    mocker.patch("sys.argv", ["checkinternet", "display", "--yaml_file", "in.yaml"])
    mocker.patch(
        "internet_troubleshooter.checkinternet.display",
        return_value=3,
    )

    with pytest.raises(SystemExit) as excinfo:
        checkinternet.main()
    assert excinfo.value.code == 3
