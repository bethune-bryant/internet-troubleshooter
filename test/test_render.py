import builtins
import io

import pytest

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.render import (
    PLOT_PACKET_LOSS_PCT,
    _build_trace_tables_html,
    _format_summary_stats,
    _metric_status,
    _packet_loss_axis_max,
    _ping_target,
    _trace_rows,
    to_html,
    to_human,
    trace_name,
)
from internet_troubleshooter.result import TestResult as InternetTestResult
from internet_troubleshooter.speed_test import SpeedResult
from internet_troubleshooter.trace_test import TraceResult


def make_result(time_stamp, packet_loss=None, speed=None, hops=None, ip="8.8.8.8"):
    """A TestResult holding only the pieces a test cares about.

    speed is (download, upload, latency); hops is a list of (ip, packet_loss)
    pairs, where None stands for a hop that could not be pinged.
    """
    ping_result = None
    if packet_loss is not None:
        ping_result = PingResult(ip=ip, packet_loss=packet_loss)

    speed_result = None
    if speed is not None:
        download, upload, latency = speed
        speed_result = SpeedResult(download=download, upload=upload, latency=latency)

    trace_result = None
    if hops is not None:
        trace_result = TraceResult(
            ping_results=[
                None if hop is None else PingResult(ip=hop[0], packet_loss=hop[1])
                for hop in hops
            ]
        )

    return InternetTestResult(
        ping_result=ping_result,
        trace_result=trace_result,
        speed_result=speed_result,
        time_stamp=time_stamp,
    )


def render(results):
    output = io.StringIO()
    to_html(results, output)
    return output.getvalue()


def test_trace_name():
    assert trace_name("Download", [1.0, 2.0]) == "Download (avg: 1.50)"
    assert trace_name("Download", []) == "Download"


def test_to_html_with_no_data():
    results = [make_result(2.0), make_result(1.0)]

    text = render(results)
    assert text.startswith("<!DOCTYPE html>")
    assert "<title>Internet Status</title>" in text
    assert "<h1>Internet Status</h1>" in text
    assert "No results to summarize yet." not in text
    assert [result.time_stamp for result in results] == [2.0, 1.0]


def test_to_html_with_data():
    results = [make_result(2.0, packet_loss=10.0), make_result(1.0, packet_loss=0.0)]

    assert "Packet Loss (avg: 5.00)" in render(results)


def test_to_html_uses_a_dark_theme():
    text = render([make_result(1.0, packet_loss=1.0)])

    assert '<html lang="en" data-theme="dark">' in text
    assert '<meta name="color-scheme" content="dark">' in text
    assert '<body class="dark">' in text
    assert "--bg: #0f1117;" in text
    # The charts carry the same dark background as the page around them.
    assert '"plot_bgcolor":"#131620"' in text
    assert '"paper_bgcolor":"#171a23"' in text


def test_to_html_summary_cards_report_mean_min_and_max():
    results = [
        make_result(1.0, packet_loss=0.0, speed=(80.0, 20.0, 10.0)),
        make_result(2.0, packet_loss=4.0, speed=(60.0, 10.0, 30.0)),
    ]

    text = render(results)
    assert '<section class="panel" id="summary">' in text
    assert '<h3 class="card__label">Download</h3>' in text
    assert (
        '<p class="card__value">70.00<span class="card__unit">Mbps</span></p>' in text
    )
    assert "<dd>60.00Mbps</dd>" in text
    assert "<dd>80.00Mbps</dd>" in text
    assert "<dd>2</dd>" in text
    assert "Target &ge; 50Mbps" in text
    assert '<span class="chip">Target 8.8.8.8</span>' in text
    assert '<span class="chip">2 run(s)</span>' in text


def test_to_html_summary_flags_healthy_and_unhealthy_metrics():
    text = render([make_result(1.0, packet_loss=25.0, speed=(80.0, 2.0, 5.0))])

    assert '<article class="card card--good">' in text
    assert '<article class="card card--bad">' in text
    assert '<span class="chip">1 incomplete run(s)</span>' not in text


def test_to_html_summary_marks_missing_measurements():
    text = render([make_result(1.0)])

    assert '<article class="card card--empty">' in text
    assert '<p class="card__value">&mdash;' in text
    assert '<span class="chip">1 incomplete run(s)</span>' in text


def test_to_html_with_no_results_at_all():
    text = render([])

    assert "No results to summarize yet." in text
    assert '<span class="chip">0 run(s)</span>' in text


def test_to_html_trace_table_is_scrollable_and_selectable():
    results = [
        make_result(
            1.0,
            packet_loss=20.0,
            hops=[("192.168.1.1", 0.0), ("10.0.0.1", 12.5)],
        ),
        make_result(2.0, packet_loss=30.0, hops=[("192.168.1.1", 1.0)]),
    ]

    text = render(results)
    assert '<div class="table-scroll">' in text
    assert '<table class="trace">' in text
    assert "max-height: 460px; overflow: auto;" in text
    assert "position: sticky; top: 0;" in text
    assert '<th scope="row" class="col-hop">1</th>' in text
    assert '<span class="hop-ip">192.168.1.1</span>' in text
    assert '<span class="hop-ip">10.0.0.1</span>' in text
    assert '<span class="loss loss--bad">12.50%</span>' in text
    assert '<span class="loss">0.00%</span>' in text
    # The second run has no second hop, so that cell is blank.
    assert '<td class="cell--missing">&mdash;</td>' in text
    assert '<span class="chip">2 traced run(s)</span>' in text
    assert '<span class="chip">2 hop(s) deep</span>' in text
    assert "<go.Table" not in text


def test_to_html_escapes_hop_addresses():
    text = render([make_result(1.0, packet_loss=5.0, hops=[("<b>evil</b>", 0.0)])])

    assert "<b>evil</b>" not in text
    assert "&lt;b&gt;evil&lt;/b&gt;" in text


def test_to_html_without_traces_explains_the_empty_table():
    text = render([make_result(1.0, packet_loss=0.0)])

    assert '<span class="chip">No traces recorded</span>' in text
    assert "none were recorded for these results" in text
    assert '<table class="trace">' not in text


def test_to_html_includes_plotly_from_the_cdn_once():
    text = render([make_result(1.0, packet_loss=1.0, speed=(1.0, 2.0, 3.0))])

    assert text.count("cdn.plot.ly/plotly-") == 1


def test_to_html_writes_to_a_path(tmp_path):
    report = tmp_path / "report.html"

    to_html([make_result(1.0, packet_loss=1.0)], str(report))

    assert report.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_to_html_without_plotly(mocker):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.split(".")[0] == "plotly":
            raise ImportError("No module named 'plotly'")
        return real_import(name, *args, **kwargs)

    mocker.patch("builtins.__import__", side_effect=fake_import)

    with pytest.raises(RuntimeError) as excinfo:
        to_html([make_result(1.0)], io.StringIO())

    assert str(excinfo.value) == (
        "HTML output requires plotly, which is not installed. "
        "Install it with 'pip install internet-troubleshooter[html]' "
        "or 'pip install plotly'."
    )
    assert isinstance(excinfo.value.__cause__, ImportError)


def test_packet_loss_axis_max():
    assert _packet_loss_axis_max([]) == 6
    assert _packet_loss_axis_max([1.0, 2.0]) == 6
    assert _packet_loss_axis_max([40.0]) == 46.0
    assert _packet_loss_axis_max([99.0]) == 100


def test_metric_status():
    assert _metric_status(None, 50, True) == "empty"
    assert _metric_status(60.0, 50, True) == "good"
    assert _metric_status(40.0, 50, True) == "bad"
    assert _metric_status(1.0, 3, False) == "good"
    assert _metric_status(5.0, 3, False) == "bad"


def test_ping_target_requires_agreement():
    assert _ping_target([make_result(1.0, packet_loss=0.0)]) == "8.8.8.8"
    assert _ping_target([make_result(1.0)]) is None
    assert (
        _ping_target(
            [
                make_result(1.0, packet_loss=0.0),
                make_result(2.0, packet_loss=0.0, ip="1.1.1.1"),
            ]
        )
        is None
    )


def test_format_summary_stats_reports_run_metadata():
    results = [
        make_result(1.0, packet_loss=0.0, speed=(80.0, 20.0, 10.0)),
        make_result(2.0, packet_loss=4.0),
    ]

    summary = _format_summary_stats(results)
    assert summary["runs"] == 2
    assert summary["incomplete"] == 1
    assert summary["ping_target"] == "8.8.8.8"
    assert summary["first_run"] < summary["last_run"]

    download = summary["metrics"][0]
    assert download["label"] == "Download"
    assert download["samples"] == 1
    assert download["mean"] == 80.0

    empty = _format_summary_stats([])
    assert empty["first_run"] is None
    assert empty["last_run"] is None
    assert empty["metrics"][0]["mean"] is None
    assert empty["metrics"][0]["minimum"] is None


def test_trace_rows_pads_shorter_traces():
    results = [
        make_result(1.0, hops=[("10.0.0.1", 0.0), ("10.0.0.2", 1.0)]),
        make_result(2.0, hops=[("10.0.0.1", 2.0)]),
    ]

    rows = _trace_rows(results)
    assert [hop_number for hop_number, _ in rows] == [1, 2]
    assert [ping.ip for ping in rows[0][1]] == ["10.0.0.1", "10.0.0.1"]
    assert rows[1][1][1] is None


def test_build_trace_tables_html_marks_hops_over_the_threshold():
    results = [
        make_result(
            1.0,
            hops=[
                ("10.0.0.1", PLOT_PACKET_LOSS_PCT),
                ("10.0.0.2", PLOT_PACKET_LOSS_PCT + 1),
                None,
            ],
        )
    ]

    table = _build_trace_tables_html(results)
    assert table.count('class="loss"') == 1
    assert table.count('class="loss loss--bad"') == 1
    assert table.count('class="cell--missing"') == 1


def test_to_human():
    results = [make_result(1.0, packet_loss=10.0), make_result(2.0, packet_loss=20.0)]

    output = io.StringIO()
    to_human(results, output)
    text = output.getvalue()
    assert "Mean: 15.00%" in text
    assert "Download: Not enough data." in text
