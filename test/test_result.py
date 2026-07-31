import io
import logging
from time import sleep

import pytest
import yaml

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.result import TestResult as InternetTestResult
from internet_troubleshooter.speed_test import SpeedResult
from internet_troubleshooter.trace_test import TraceResult


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


SPEEDTEST_PAYLOAD = {
    "isp": "MyISP",
    "interface": {
        "externalIp": "555.555.555.555",
        "internalIp": "192.168.1.1",
        "macAddr": "AA:AA:AA:AA:AA:AA",
    },
    "server": {"name": "Conterra", "location": "Stemmons, TX"},
    "packetLoss": 0,
}


def make_full_result(time_stamp=1700000000.0):
    return InternetTestResult(
        ping_result=PingResult(ip="8.8.8.8", packet_loss=1.5),
        trace_result=TraceResult(
            ping_results=[PingResult(ip="10.0.0.1", packet_loss=0.0), None]
        ),
        speed_result=SpeedResult(upload=17.1212, download=58.542856, latency=19.266),
        time_stamp=time_stamp,
    )


def write_results(path, results):
    with open(path, "a", encoding="utf-8") as f:
        for result in results:
            print("---\n{}\n...\n".format(result.to_yaml()), file=f)


def test_timestamp_is_per_instance():
    first = InternetTestResult(ping_result=None, trace_result=None, speed_result=None)
    sleep(0.01)
    second = InternetTestResult(ping_result=None, trace_result=None, speed_result=None)
    assert first.time_stamp != second.time_stamp
    assert first.time_stamp < second.time_stamp


def test_human_readable_skips_missing_hops():
    result = InternetTestResult(
        ping_result=PingResult(ip="8.8.8.8", packet_loss=5.0),
        trace_result=TraceResult(
            ping_results=[None, PingResult(ip="10.0.0.1", packet_loss=1.5), None]
        ),
        speed_result=None,
    )

    output = io.StringIO()
    result.human_readable(output)
    text = output.getvalue()
    assert "Packet Loss: 5.00%" in text
    assert "1.50% 10.0.0.1" in text


def test_human_readable_reports_the_speedtest_context():
    result = InternetTestResult(
        ping_result=None,
        trace_result=None,
        speed_result=SpeedResult(
            upload=17.1212,
            download=58.542856,
            latency=19.266,
            raw_result=SPEEDTEST_PAYLOAD,
        ),
    )

    output = io.StringIO()
    result.human_readable(output)
    text = output.getvalue()
    assert "Download:    58.54Mbps" in text
    assert "Server:      Conterra (Stemmons, TX)" in text
    assert "ISP:         MyISP" in text
    assert "External IP: 555.555.555.555" in text


def test_speed_result_payload_round_trips_through_yaml(tmp_path):
    yaml_file = tmp_path / "results.yaml"
    result = make_full_result()
    result.speed_result = SpeedResult(
        upload=17.1212,
        download=58.542856,
        latency=19.266,
        raw_result=SPEEDTEST_PAYLOAD,
    )
    write_results(yaml_file, [result])

    text = yaml_file.read_text(encoding="utf-8")
    assert "raw_result:" in text
    assert "AA:AA:AA:AA:AA:AA" in text
    assert "!!python/object" not in text

    loaded = InternetTestResult.load_results(str(yaml_file))
    assert loaded == [result]
    assert loaded[0].speed_result.raw_result == SPEEDTEST_PAYLOAD


def test_to_dict_uses_snake_case_keys():
    data = make_full_result().to_dict()

    assert sorted(data) == ["ping_result", "speed_result", "time_stamp", "trace_result"]
    assert data["ping_result"] == {"ip": "8.8.8.8", "packet_loss": 1.5}
    assert data["trace_result"] == {
        "ping_results": [{"ip": "10.0.0.1", "packet_loss": 0.0}, None]
    }
    assert data["speed_result"] == {
        "upload": 17.1212,
        "download": 58.542856,
        "latency": 19.266,
    }


def test_from_dict_round_trip():
    result = make_full_result()
    assert InternetTestResult.from_dict(result.to_dict()) == result


def test_from_dict_without_timestamp_uses_now():
    data = make_full_result().to_dict()
    del data["time_stamp"]

    assert InternetTestResult.from_dict(data).time_stamp > 1700000000.0


def test_from_dict_with_empty_result():
    result = InternetTestResult.from_dict({"time_stamp": 1.0})
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
    assert [result.time_stamp for result in loaded] == [1700000000.0, 1700000060.0]


def test_load_results_reads_utf8(tmp_path):
    yaml_file = tmp_path / "results.yaml"
    result = make_result(1.0, packet_loss=1.0)
    result.ping_result.ip = "rout\u00e9r.local"
    write_results(yaml_file, [result])

    loaded = InternetTestResult.load_results(str(yaml_file))
    assert loaded[0].ping_result.ip == "rout\u00e9r.local"


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
        InternetTestResult.load_yaml("ping_result: [unclosed")
