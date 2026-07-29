import builtins
import io

import pytest

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.render import to_html, to_human, trace_name
from internet_troubleshooter.result import TestResult as InternetTestResult


def make_result(time_stamp, packet_loss=None):
    ping_result = None
    if packet_loss is not None:
        ping_result = PingResult(ip="8.8.8.8", packet_loss=packet_loss)
    return InternetTestResult(
        ping_result=ping_result,
        trace_result=None,
        speed_result=None,
        time_stamp=time_stamp,
    )


def test_trace_name():
    assert trace_name("Download", [1.0, 2.0]) == "Download (avg: 1.50)"
    assert trace_name("Download", []) == "Download"


def test_to_html_with_no_data():
    results = [make_result(2.0), make_result(1.0)]

    output = io.StringIO()
    to_html(results, output)
    assert "Internet Status" in output.getvalue()
    assert [result.time_stamp for result in results] == [2.0, 1.0]


def test_to_html_with_data():
    results = [make_result(2.0, packet_loss=10.0), make_result(1.0, packet_loss=0.0)]

    output = io.StringIO()
    to_html(results, output)
    assert "Packet Loss (avg: 5.00)" in output.getvalue()


def test_to_html_without_plotly(mocker):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.split(".")[0] == "plotly":
            raise ImportError("No module named 'plotly'")
        return real_import(name, *args, **kwargs)

    mocker.patch("builtins.__import__", side_effect=fake_import)

    with pytest.raises(RuntimeError) as excinfo:
        to_html([make_result(1.0)], io.StringIO())

    assert str(excinfo.value) == (
        "HTML output requires plotly, which is not installed. "
        "Install it with 'pip install internet-troubleshooter[html]' "
        "or 'pip install plotly'."
    )
    assert isinstance(excinfo.value.__cause__, ImportError)


def test_to_human():
    results = [make_result(1.0, packet_loss=10.0), make_result(2.0, packet_loss=20.0)]

    output = io.StringIO()
    to_human(results, output)
    text = output.getvalue()
    assert "Mean: 15.00%" in text
    assert "Download: Not enough data." in text
