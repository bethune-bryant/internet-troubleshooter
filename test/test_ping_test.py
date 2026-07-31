from subprocess import CompletedProcess
from internet_troubleshooter.ping_test import PingResult


# What `ping -f -q -c 400` prints as root; the flood ping appends its own
# figures to the round trip line.
FLOOD_PING_OUTPUT = """PING google.com (172.217.1.142) 56(84) bytes of data.

--- google.com ping statistics ---
400 packets transmitted, 400 received, 12.34% packet loss, time 6659ms
rtt min/avg/max/mdev = 16.544/20.312/35.193/2.061 ms, pipe 3, ipg/ewma 16.690/20.405 ms"""

# What `ping -q -c 10` prints as a normal user.
QUIET_PING_OUTPUT = """PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.

--- 8.8.8.8 ping statistics ---
10 packets transmitted, 10 received, 0% packet loss, time 9013ms
rtt min/avg/max/mdev = 10.123/15.456/20.789/2.345 ms"""

# A ping that lost everything reports no round trip line at all.
TOTAL_LOSS_PING_OUTPUT = """PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.

--- 8.8.8.8 ping statistics ---
10 packets transmitted, 0 received, 100% packet loss, time 9200ms"""


def test_PingResult():
    x = PingResult(ip="1.1.1.1", packet_loss=10)
    assert x.ip == "1.1.1.1"
    assert x.packet_loss == 10
    assert str(x) == "10.00%: 1.1.1.1"
    assert x.rtt_min_ms is None
    assert x.rtt_avg_ms is None
    assert x.rtt_max_ms is None
    assert x.rtt_mdev_ms is None


def test_summarize():
    x = [
        PingResult(ip="1.1.1.1", packet_loss=10),
        PingResult(ip="1.1.1.2", packet_loss=15),
        PingResult(ip="1.1.1.3", packet_loss=20),
    ]
    summary = PingResult.summarize(x)
    assert "Packet Loss:" in summary
    assert "Mean: 15.00%" in summary
    assert "Variance: 25.00%" in summary
    assert "Min: 10.00%" in summary
    assert "Max: 20.00%" in summary


def test_summarize_reports_the_round_trip_times():
    x = [
        PingResult(ip="1.1.1.1", packet_loss=10, rtt_avg_ms=10.0),
        PingResult(ip="1.1.1.2", packet_loss=15, rtt_avg_ms=20.0),
    ]
    summary = PingResult.summarize(x)
    assert "Ping RTT:" in summary
    assert "Mean: 15.00ms" in summary
    assert "Min: 10.00ms" in summary
    assert "Max: 20.00ms" in summary


def test_summarize_without_any_round_trip_times():
    x = [
        PingResult(ip="1.1.1.1", packet_loss=10),
        PingResult(ip="1.1.1.2", packet_loss=15),
    ]

    assert "Ping RTT: Not enough data." in PingResult.summarize(x)


def test_parseResult():
    x = PingResult.parse_result("google.com", FLOOD_PING_OUTPUT)
    assert x.ip == "google.com"
    assert x.packet_loss == 12.34
    assert x.rtt_min_ms == 16.544
    assert x.rtt_avg_ms == 20.312
    assert x.rtt_max_ms == 35.193
    assert x.rtt_mdev_ms == 2.061


def test_parseResultNonRoot():
    x = PingResult.parse_result("8.8.8.8", QUIET_PING_OUTPUT)
    assert x.packet_loss == 0
    assert x.rtt_min_ms == 10.123
    assert x.rtt_avg_ms == 15.456
    assert x.rtt_max_ms == 20.789
    assert x.rtt_mdev_ms == 2.345


def test_parseResultWithoutRoundTripTimes():
    x = PingResult.parse_result("8.8.8.8", TOTAL_LOSS_PING_OUTPUT)
    assert x.packet_loss == 100
    assert x.rtt_min_ms is None
    assert x.rtt_avg_ms is None
    assert x.rtt_max_ms is None
    assert x.rtt_mdev_ms is None


def test_parseResultWithoutDeviation():
    test_output = """--- 8.8.8.8 ping statistics ---
5 packets transmitted, 5 received, 0% packet loss
round-trip min/avg/max = 10.1/15.2/20.3 ms"""

    x = PingResult.parse_result("8.8.8.8", test_output)
    assert x.rtt_min_ms == 10.1
    assert x.rtt_avg_ms == 15.2
    assert x.rtt_max_ms == 20.3
    assert x.rtt_mdev_ms is None


def test_parseResultBad():
    test_output = """Some malformed input"""

    x = PingResult.parse_result("google.com", test_output)
    assert x is None


def test_to_dict_logs_the_round_trip_times():
    x = PingResult.parse_result("8.8.8.8", QUIET_PING_OUTPUT)

    assert x.to_dict() == {
        "ip": "8.8.8.8",
        "packet_loss": 0.0,
        "rtt_min_ms": 10.123,
        "rtt_avg_ms": 15.456,
        "rtt_max_ms": 20.789,
        "rtt_mdev_ms": 2.345,
    }
    assert PingResult.from_dict(x.to_dict()) == x


def test_to_dict_omits_unmeasured_round_trip_times():
    x = PingResult(ip="8.8.8.8", packet_loss=100.0, rtt_avg_ms=15.0)

    assert x.to_dict() == {"ip": "8.8.8.8", "packet_loss": 100.0, "rtt_avg_ms": 15.0}


def test_from_dict_without_round_trip_times():
    x = PingResult.from_dict({"ip": "8.8.8.8", "packet_loss": 1.5})

    assert x == PingResult(ip="8.8.8.8", packet_loss=1.5)
    assert x.rtt_avg_ms is None


def test_from_dict_reads_round_trip_times_as_floats():
    x = PingResult.from_dict(
        {"ip": "8.8.8.8", "packet_loss": 0, "rtt_avg_ms": 15, "rtt_max_ms": "20.5"}
    )

    assert x.rtt_avg_ms == 15.0
    assert x.rtt_max_ms == 20.5
    assert x.rtt_min_ms is None


def test_execute_test_missing_binary(mocker, capsys):
    mocker.patch("os.geteuid", return_value=0)
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)

    x = PingResult.execute_test("8.8.8.8")
    assert x is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "ping" in captured.err


def test_run_test_missing_binary(mocker, capsys):
    mocker.patch("os.geteuid", return_value=0)
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)

    x = PingResult.run_test("8.8.8.8")
    assert x is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "Cannot find packet loss" not in captured.err


def test_execute_test(mocker, capsys):
    test_output = """TEST STRING"""

    mocker.patch("os.geteuid", return_value=1000)
    mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(None, returncode=0, stdout=test_output),
    )

    x = PingResult.execute_test("8.8.8.8")
    assert test_output == x
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "WARNING" in captured.err


def test_run_test_parse_failure(mocker, capsys):
    mocker.patch("os.geteuid", return_value=0)
    mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(None, returncode=0, stdout="MALFORMED"),
    )

    x = PingResult.run_test("8.8.8.8")
    assert x is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Cannot find packet loss" in captured.err


def test_execute_test_root(mocker, capsys):
    test_output = """TEST STRING"""

    mocker.patch("os.geteuid", return_value=0)
    mocker.patch(
        "subprocess.run",
        return_value=CompletedProcess(None, returncode=0, stdout=test_output),
    )

    x = PingResult.execute_test("8.8.8.8")
    assert test_output == x
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "WARNING" not in captured.err
