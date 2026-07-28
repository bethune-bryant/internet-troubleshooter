import io
from time import sleep

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.result import TestResult as InternetTestResult
from internet_troubleshooter.result import trace_name
from internet_troubleshooter.trace_test import TraceResult


def make_result(timeStamp, packetLoss=None):
    pingResult = None
    if packetLoss is not None:
        pingResult = PingResult(ip="8.8.8.8", packetLoss=packetLoss)
    return InternetTestResult(
        pingResult=pingResult,
        traceResult=None,
        speedResult=None,
        timeStamp=timeStamp,
    )


def test_timestamp_is_per_instance():
    first = InternetTestResult(pingResult=None, traceResult=None, speedResult=None)
    sleep(0.01)
    second = InternetTestResult(pingResult=None, traceResult=None, speedResult=None)
    assert first.timeStamp != second.timeStamp
    assert first.timeStamp < second.timeStamp


def test_human_readable_skips_missing_hops():
    result = InternetTestResult(
        pingResult=PingResult(ip="8.8.8.8", packetLoss=5.0),
        traceResult=TraceResult(
            pingResults=[None, PingResult(ip="10.0.0.1", packetLoss=1.5), None]
        ),
        speedResult=None,
    )

    output = io.StringIO()
    result.human_readable(output)
    text = output.getvalue()
    assert "Packet Loss: 5.00%" in text
    assert "1.50% 10.0.0.1" in text


def test_trace_name():
    assert trace_name("Download", [1.0, 2.0]) == "Download (avg: 1.50)"
    assert trace_name("Download", []) == "Download"


def test_to_html_with_no_data():
    results = [make_result(2.0), make_result(1.0)]

    output = io.StringIO()
    InternetTestResult.to_html(results, output)
    assert "Internet Status" in output.getvalue()
    assert [result.timeStamp for result in results] == [2.0, 1.0]


def test_to_html_with_data():
    results = [make_result(2.0, packetLoss=10.0), make_result(1.0, packetLoss=0.0)]

    output = io.StringIO()
    InternetTestResult.to_html(results, output)
    assert "Packet Loss (avg: 5.00)" in output.getvalue()


def test_to_human():
    results = [make_result(1.0, packetLoss=10.0), make_result(2.0, packetLoss=20.0)]

    output = io.StringIO()
    InternetTestResult.to_human(results, output)
    text = output.getvalue()
    assert "Mean: 15.00%" in text
    assert "Download: Not enough data." in text
