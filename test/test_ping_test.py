

def test_PingResult():
    x = PingResult(ip="1.1.1.1", count=10)
    assert x.ip == "1.1.1.1"
    assert x.count == 10