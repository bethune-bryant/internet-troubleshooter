from argparse import Namespace

from internet_troubleshooter import checkinternet
from internet_troubleshooter.ping_test import PingResult


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


def run_with_ping(mocker, ping_result):
    mocker.patch(
        "internet_troubleshooter.checkinternet.PingResult.run_test",
        return_value=ping_result,
    )
    trace = mocker.patch(
        "internet_troubleshooter.checkinternet.TraceResult.run_test",
        return_value=None,
    )
    checkinternet.run(make_args())
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
