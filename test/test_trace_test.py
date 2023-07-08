from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult


def test_TraceResult():
    x = TraceResult([PingResult(ip="1.1.1.1", packetLoss=10)])
    assert x.pingResults[0].ip == "1.1.1.1"
    assert x.pingResults[0].packetLoss == 10
