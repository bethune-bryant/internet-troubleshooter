import json
from subprocess import CompletedProcess

import pytest
import yaml

from internet_troubleshooter.speed_test import SpeedResult

test_json = """
{
   "type":"result",
   "timestamp":"2023-07-08T20:07:29Z",
   "ping":{
      "jitter":1.306,
      "latency":19.266,
      "low":17.387,
      "high":22.368
   },
   "download":{
      "bandwidth":7317857,
      "bytes":74558968,
      "elapsed":10610,
      "latency":{
         "iqm":58.422,
         "low":19.483,
         "high":283.500,
         "jitter":14.344
      }
   },
   "upload":{
      "bandwidth":2140150,
      "bytes":10269216,
      "elapsed":4807,
      "latency":{
         "iqm":72.092,
         "low":22.028,
         "high":311.506,
         "jitter":24.518
      }
   },
   "packetLoss":0,
   "isp":"MyISP",
   "interface":{
      "internalIp":"192.168.1.1",
      "name":"enp3s0",
      "macAddr":"AA:AA:AA:AA:AA:AA",
      "isVpn":false,
      "externalIp":"555.555.555.555"
   },
   "server":{
      "id":27863,
      "host":"speedtest-stemmons-tx.conterra.com",
      "port":8080,
      "name":"Conterra",
      "location":"Stemmons, TX",
      "country":"United States",
      "ip":"69.194.191.83"
   },
   "result":{
      "id":"555-555",
      "url":"https://www.speedtest.net/result/c/555-555",
      "persisted":true
   }
}
    """


def test_SpeedResult():
    x = SpeedResult(results=test_json)
    assert x.download == pytest.approx(58.542856)
    assert x.upload == pytest.approx(17.1212)
    assert x.latency == pytest.approx(19.266)
    assert str(x).startswith(
        "Download:    {}Mbps\nUpload:      {}Mbps\nLatency:     {}ms".format(
            58.54,
            17.12,
            19.27,
        )
    )


def test_SpeedResult_without_raw_json_prints_only_measurements():
    x = SpeedResult(upload=17.1212, download=58.542856, latency=19.266)
    assert x.raw_result is None
    assert str(x) == (
        "Download:    {}Mbps\nUpload:      {}Mbps\nLatency:     {}ms".format(
            58.54,
            17.12,
            19.27,
        )
    )


def test_SpeedResult_retains_the_whole_payload():
    x = SpeedResult(results=test_json)

    assert x.raw_result == json.loads(test_json)
    assert x.raw_result["interface"]["macAddr"] == "AA:AA:AA:AA:AA:AA"
    assert x.raw_result["interface"]["externalIp"] == "555.555.555.555"
    assert x.raw_result["isp"] == "MyISP"
    assert x.raw_result["server"]["name"] == "Conterra"
    assert x.raw_result["result"]["url"] == (
        "https://www.speedtest.net/result/c/555-555"
    )


def test_SpeedResult_to_dict_keeps_the_whole_payload():
    x = SpeedResult(results=test_json)
    assert x.to_dict() == {
        "upload": pytest.approx(17.1212),
        "download": pytest.approx(58.542856),
        "latency": pytest.approx(19.266),
        "raw_result": json.loads(test_json),
    }


def test_SpeedResult_to_dict_omits_the_payload_when_there_is_none():
    x = SpeedResult(upload=1.0, download=2.0, latency=3.0)
    assert x.to_dict() == {"upload": 1.0, "download": 2.0, "latency": 3.0}


def test_SpeedResult_from_dict_round_trip():
    x = SpeedResult(results=test_json)
    restored = SpeedResult.from_dict(x.to_dict())

    assert restored == x
    assert restored.raw_result == json.loads(test_json)


def test_SpeedResult_from_dict_round_trip_through_yaml():
    x = SpeedResult(results=test_json)
    restored = SpeedResult.from_dict(yaml.safe_load(yaml.safe_dump(x.to_dict())))

    assert restored == x
    assert restored.raw_result == json.loads(test_json)


def test_SpeedResult_from_dict_without_raw_result():
    """Results logged before the payload was recorded still load."""
    x = SpeedResult.from_dict({"upload": 1.0, "download": 2.0, "latency": 3.0})

    assert x == SpeedResult(upload=1.0, download=2.0, latency=3.0)
    assert x.raw_result is None
    assert x.context() == []


def test_SpeedResult_context_reports_where_the_test_ran():
    x = SpeedResult(results=test_json)

    assert x.server == "Conterra (Stemmons, TX)"
    assert x.isp == "MyISP"
    assert x.external_ip == "555.555.555.555"
    assert x.context() == [
        ("Server", "Conterra (Stemmons, TX)"),
        ("ISP", "MyISP"),
        ("External IP", "555.555.555.555"),
    ]
    assert str(x).endswith(
        "\nServer:      Conterra (Stemmons, TX)"
        "\nISP:         MyISP"
        "\nExternal IP: 555.555.555.555"
    )


@pytest.mark.parametrize(
    "raw_result, expected",
    [
        (None, None),
        ({}, None),
        ({"server": {}}, None),
        ({"server": {"name": "", "location": ""}}, None),
        ({"server": {"name": "Conterra"}}, "Conterra"),
        ({"server": {"location": "Stemmons, TX"}}, "Stemmons, TX"),
        ({"server": "not a mapping"}, None),
    ],
)
def test_SpeedResult_server_tolerates_partial_payloads(raw_result, expected):
    x = SpeedResult(upload=1.0, download=2.0, latency=3.0, raw_result=raw_result)
    assert x.server == expected


@pytest.mark.parametrize(
    "bad_results",
    [
        "not json at all",
        "",
        "[]",
        '{"ping": {"latency": 1.0}}',
        '{"upload": {"bandwidth": 1}, "download": {"bandwidth": 1}, "ping": {}}',
        '{"upload": {"bandwidth": "fast"}, "download": {"bandwidth": 1},'
        ' "ping": {"latency": 1.0}}',
        '{"upload": {"bandwidth": {}}, "download": {"bandwidth": 1},'
        ' "ping": {"latency": 1.0}}',
    ],
)
def test_SpeedResult_rejects_bad_json(bad_results, capsys):
    with pytest.raises(ValueError):
        SpeedResult(results=bad_results)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR: Unable to parse speedtest output" in captured.err


def test_run_test_returns_none_on_bad_json(mocker, capsys):
    mocker.patch(
        "internet_troubleshooter.speed_test.SpeedResult.execute_test",
        return_value="not json at all",
    )

    assert SpeedResult.run_test() is None

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR: Unable to parse speedtest output" in captured.err


def test_summarize_units():
    results = [
        SpeedResult(upload=1.0, download=10.0, latency=20.0),
        SpeedResult(upload=3.0, download=30.0, latency=40.0),
    ]

    text = SpeedResult.summarize(results)
    assert "Download:\n  Mean: 20.00Mbps" in text
    assert "Upload:\n  Mean: 2.00Mbps" in text
    assert "Latency:\n  Mean: 30.00ms" in text
    assert "Mbps" not in text.split("Latency:")[1]


def test_check(mocker, capsys):
    test_output = "HELP TEXT"

    mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(None, returncode=0, stdout=test_output),
    )

    x = SpeedResult.check()
    assert x
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_check_missing_binary(mocker, capsys):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)

    x = SpeedResult.check()
    assert not x
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "speedtest" in captured.err
    assert "WARNING:" in captured.err
    assert "https://www.speedtest.net/apps/cli" in captured.err


def test_execute_test_missing_binary(mocker, capsys):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)

    assert SpeedResult.execute_test() is None
    assert SpeedResult.run_test() is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err


def test_execute_test_success(mocker, capsys):
    mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(None, returncode=0, stdout=test_json, stderr=""),
    )

    assert SpeedResult.execute_test() == test_json
    assert SpeedResult.run_test() == SpeedResult(results=test_json)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_execute_test_error(mocker, capsys):
    test_output = """partial speedtest output"""
    error_output = """Configuration - No servers defined"""

    mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            None, returncode=1, stdout=test_output, stderr=error_output
        ),
    )

    assert SpeedResult.execute_test() is None
    assert SpeedResult.run_test() is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR: Error running speedtest" in captured.err
    assert test_output in captured.err
    assert error_output in captured.err


def test_check_error(mocker, capsys):
    test_output = ""
    error_output = """speedtest not found"""

    mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(
            None, returncode=1, stdout=test_output, stderr=error_output
        ),
    )

    x = SpeedResult.check()
    assert not x
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "WARNING:" in captured.err
    assert "https://www.speedtest.net/apps/cli" in captured.err
