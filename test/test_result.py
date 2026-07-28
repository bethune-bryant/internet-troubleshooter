import io
import logging
from time import sleep

import pytest
import yaml

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.result import TestResult as InternetTestResult
from internet_troubleshooter.result import trace_name
from internet_troubleshooter.speed_test import SpeedResult
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


def make_full_result(timeStamp=1700000000.0):
    return InternetTestResult(
        pingResult=PingResult(ip="8.8.8.8", packetLoss=1.5),
        traceResult=TraceResult(
            pingResults=[PingResult(ip="10.0.0.1", packetLoss=0.0), None]
        ),
        speedResult=SpeedResult(upload=17.1212, download=58.542856, latency=19.266),
        timeStamp=timeStamp,
    )


def write_results(path, results):
    with open(path, "a", encoding="utf-8") as f:
        for result in results:
            print("---\n{}\n...\n".format(result.to_yaml()), file=f)


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


def test_to_dict_uses_camel_case_keys():
    data = make_full_result().to_dict()

    assert sorted(data) == ["pingResult", "speedResult", "timeStamp", "traceResult"]
    assert data["pingResult"] == {"ip": "8.8.8.8", "packetLoss": 1.5}
    assert data["traceResult"] == {
        "pingResults": [{"ip": "10.0.0.1", "packetLoss": 0.0}, None]
    }
    assert data["speedResult"] == {
        "upload": 17.1212,
        "download": 58.542856,
        "latency": 19.266,
    }


def test_from_dict_round_trip():
    result = make_full_result()
    assert InternetTestResult.from_dict(result.to_dict()) == result


def test_from_dict_without_timestamp_uses_now():
    data = make_full_result().to_dict()
    del data["timeStamp"]

    assert InternetTestResult.from_dict(data).timeStamp > 1700000000.0


def test_from_dict_with_empty_result():
    result = InternetTestResult.from_dict({"timeStamp": 1.0})
    assert result == make_result(1.0)


def test_to_yaml_is_safe():
    text = make_full_result().to_yaml()

    assert "!!python/object" not in text
    assert yaml.safe_load(text) == make_full_result().to_dict()


def test_yaml_round_trip_through_file(tmp_path):
    yaml_file = tmp_path / "results.yaml"
    results = [make_full_result(1700000000.0), make_full_result(1700000060.0)]
    write_results(yaml_file, results)

    assert "!!python/object" not in yaml_file.read_text(encoding="utf-8")
    assert InternetTestResult.load_results(str(yaml_file)) == results


def test_yaml_round_trip_appends(tmp_path):
    yaml_file = tmp_path / "results.yaml"
    write_results(yaml_file, [make_full_result(1700000000.0)])
    write_results(yaml_file, [make_full_result(1700000060.0)])

    loaded = InternetTestResult.load_results(str(yaml_file))
    assert [result.timeStamp for result in loaded] == [1700000000.0, 1700000060.0]


def test_load_results_reads_utf8(tmp_path):
    yaml_file = tmp_path / "results.yaml"
    result = make_result(1.0, packetLoss=1.0)
    result.pingResult.ip = "rout\u00e9r.local"
    write_results(yaml_file, [result])

    loaded = InternetTestResult.load_results(str(yaml_file))
    assert loaded[0].pingResult.ip == "rout\u00e9r.local"


def test_load_results_skips_empty_documents(tmp_path):
    yaml_file = tmp_path / "results.yaml"
    yaml_file.write_text("---\n...\n", encoding="utf-8")

    assert InternetTestResult.load_results(str(yaml_file)) == []


def test_load_current_results_logs_no_warning(tmp_path, caplog):
    yaml_file = tmp_path / "results.yaml"
    yaml_file.write_text(
        "---\n{}\n...\n".format(make_full_result().to_yaml()), encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        InternetTestResult.load_results(str(yaml_file))

    assert caplog.records == []


def test_load_yaml_rejects_python_object_tags():
    with pytest.raises(yaml.YAMLError):
        InternetTestResult.load_yaml('!!python/object/apply:os.system ["echo unsafe"]')


def test_load_yaml_rejects_malformed_yaml():
    with pytest.raises(yaml.YAMLError):
        InternetTestResult.load_yaml("pingResult: [unclosed")
