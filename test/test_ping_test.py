from subprocess import CompletedProcess
import pytest
from internet_troubleshooter.ping_test import PingResult

def test_PingResult():
    x = PingResult(ip="1.1.1.1", packetLoss=10)
    assert x.ip == "1.1.1.1"
    assert x.packetLoss == 10

def test_parseResult():
    test_output = '''PING google.com (172.217.1.142) 56(84) bytes of data.

--- google.com ping statistics ---
400 packets transmitted, 400 received, 12.34% packet loss, time 6659ms
rtt min/avg/max/mdev = 16.544/20.312/35.193/2.061 ms, pipe 3, ipg/ewma 16.690/20.405 ms'''

    x = PingResult.parse_result("google.com", test_output)
    assert x.ip == "google.com"
    assert x.packetLoss == 12.34

def test_execute_test(mocker, capsys):
    test_output = '''TEST STRING'''

    mocker.patch("os.geteuid", return_value=1000)
    mocker.patch('subprocess.run', return_value=CompletedProcess(None, returncode=0, stdout=test_output))

    x = PingResult.execute_test("8.8.8.8")
    assert test_output == x
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "WARNING" in captured.err

# def test_execute_test_failure(mocker):
#     test_output = '''TEST STRING'''

#     mocker.patch("os.geteuid", return_value=1000)
#     mocker.patch('subprocess.run', return_value=CompletedProcess(None, returncode=1, stdout=test_output))

#     with pytest.raises(SystemExit) as pytest_wrapped_e:
#             x = PingResult.execute_test("8.8.8.8")
#     assert pytest_wrapped_e.type == SystemExit
#     assert pytest_wrapped_e.value.code == 2
