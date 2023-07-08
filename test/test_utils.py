from internet_troubleshooter.utils import summarize


def test_summarize():
    x = summarize([1.0, 2.0, 3.0], title="Test")
    assert "Mean: 2.00" in x
    assert "Variance: 1.00" in x
    assert "Min: 1.00" in x
    assert "Max: 3.00" in x


def test_summarize_error():
    x = summarize([], title="Test")
    assert x == "Test: Not enough data."
    x = summarize([1.0], title="Test")
    assert x == "Test: Not enough data."
