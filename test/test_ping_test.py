from subprocess import CompletedProcess
from internet_troubleshooter.ping_test import PingResult


def test_PingResult():
    x = PingResult(ip="1.1.1.1", packetLoss=10)
    assert x.ip == "1.1.1.1"
    assert x.packetLoss == 10
    assert str(x) == "10.00%: 1.1.1.1"


def test_summarize():
    x = [
        PingResult(ip="1.1.1.1", packetLoss=10),
        PingResult(ip="1.1.1.2", packetLoss=15),
        PingResult(ip="1.1.1.3", packetLoss=20),
    ]
    summary = PingResult.summarize(x)
    assert "Packet Loss:" in summary
    assert "Mean: 15.00%" in summary
    assert "Variance: 25.00%" in summary
    assert "Min: 10.00%" in summary
    assert "Max: 20.00%" in summary


def test_parseResult():
    test_output = """PING google.com (172.217.1.142) 56(84) bytes of data.

--- google.com ping statistics ---
400 packets transmitted, 400 received, 12.34% packet loss, time 6659ms
rtt min/avg/max/mdev = 16.544/20.312/35.193/2.061 ms, pipe 3, ipg/ewma 16.690/20.405 ms"""

    x = PingResult.parse_result("google.com", test_output)
    assert x.ip == "google.com"
    assert x.packetLoss == 12.34


def test_parseResultBad():
    test_output = """Some malformed input"""

    x = PingResult.parse_result("google.com", test_output)
    assert x is None


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


# def test_execute_test_failure(mocker):
#     test_output = '''TEST STRING'''

#     mocker.patch("os.geteuid", return_value=1000)
#     mocker.patch('subprocess.run', return_value=CompletedProcess(None, returncode=1, stdout=test_output))

#     with pytest.raises(SystemExit) as pytest_wrapped_e:
#             x = PingResult.execute_test("8.8.8.8")
#     assert pytest_wrapped_e.type == SystemExit
#     assert pytest_wrapped_e.value.code == 2
