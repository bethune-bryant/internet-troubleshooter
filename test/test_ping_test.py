from internet_troubleshooter.ping_test import PingResult

def test_PingResult():
    x = PingResult(ip="1.1.1.1", packetLoss=10)
    assert x.ip == "1.1.1.1"
    assert x.packetLoss == 10