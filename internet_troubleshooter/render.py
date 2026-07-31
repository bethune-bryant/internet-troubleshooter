"""Rendering of collected results into human readable and HTML reports."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    TextIO,
    Tuple,
    Union,
    cast,
)

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.result import TestResult
from internet_troubleshooter.speed_test import SpeedResult
from internet_troubleshooter.trace_test import TraceResult
from internet_troubleshooter.utils import safe_mean

# Either an open text stream or a path to write the report to.
HtmlTarget = Union[TextIO, str, "os.PathLike[str]"]

# Reference lines drawn on the HTML plots, marking the thresholds below which a
# connection is considered to be underperforming.
PLOT_DOWNLOAD_MBPS = 50
PLOT_UPLOAD_MBPS = 15
PLOT_LATENCY_MS = 20
PLOT_PACKET_LOSS_PCT = 3

# Chart colors, matching the CSS variables below so the plots and the document
# around them read as one dark themed report.
COLOR_PANEL = "#171a23"
COLOR_PLOT = "#131620"
COLOR_GRID = "#262b38"
COLOR_TEXT = "#e6e9ef"
COLOR_MUTED = "#9aa4b8"
COLOR_DOWNLOAD = "#38bdf8"
COLOR_UPLOAD = "#a78bfa"
COLOR_LATENCY = "#fbbf24"
COLOR_PING = "#5eead4"
COLOR_LOSS = "#f472b6"
COLOR_BAD = "#f87171"

CHART_HEIGHT = 780

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

MISSING_VALUE = "&mdash;"

# Plotly hover labels are plain text, so a missing measurement is spelled out
# rather than using the em dash entity the cards and tables use.
HOVER_MISSING = "no data"

# Packet loss is plotted on its own axis; a fixed 0-100 range hides the small
# values that matter, so the axis is only stretched as far as the data needs.
MIN_PACKET_LOSS_RANGE = 5
PACKET_LOSS_HEADROOM = 1.15


@dataclass(frozen=True)
class RenderThresholds:
    """The values this report treats as a healthy connection."""

    download_mbps: float = PLOT_DOWNLOAD_MBPS
    upload_mbps: float = PLOT_UPLOAD_MBPS
    latency_ms: float = PLOT_LATENCY_MS
    packet_loss_pct: float = PLOT_PACKET_LOSS_PCT


DEFAULT_THRESHOLDS = RenderThresholds()

PAGE_CSS = """
:root {
  color-scheme: dark;
  --bg: #0f1117;
  --panel: #171a23;
  --panel-alt: #1d2230;
  --border: #262b38;
  --text: #e6e9ef;
  --muted: #9aa4b8;
  --accent: #38bdf8;
  --good: #34d399;
  --bad: #f87171;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: radial-gradient(circle at 20% -10%, #1b2030 0%, var(--bg) 55%);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.page { max-width: 1320px; margin: 0 auto; padding: 32px 24px 56px; }
.masthead { margin-bottom: 24px; }
.masthead h1 { margin: 0; font-size: 1.75rem; letter-spacing: -0.01em; }
.masthead p { margin: 6px 0 0; color: var(--muted); font-size: 0.9rem; }
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px 22px 22px;
  margin-bottom: 22px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
}
.panel__header {
  display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: 12px; margin-bottom: 16px;
}
.panel__header h2 { margin: 0; font-size: 1.05rem; font-weight: 600; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  background: var(--panel-alt); border: 1px solid var(--border);
  border-radius: 999px; padding: 3px 11px; color: var(--muted);
  font-size: 0.78rem; white-space: nowrap;
}
.cards {
  display: grid; gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
}
.card {
  background: var(--panel-alt); border: 1px solid var(--border);
  border-left: 3px solid var(--muted); border-radius: 12px; padding: 14px 16px;
}
.card--good { border-left-color: var(--good); }
.card--bad { border-left-color: var(--bad); }
.card__label {
  margin: 0; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--muted);
}
.card__value {
  margin: 6px 0 12px; font-size: 1.9rem; font-weight: 600; line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.card__unit { margin-left: 4px; font-size: 0.85rem; color: var(--muted); }
.card__stats { display: flex; gap: 18px; margin: 0; }
.card__stats dt {
  font-size: 0.66rem; letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--muted);
}
.card__stats dd {
  margin: 2px 0 0; font-size: 0.9rem; font-variant-numeric: tabular-nums;
}
.card__note { margin: 12px 0 0; font-size: 0.74rem; color: var(--muted); }
.table-scroll {
  max-height: 460px; overflow: auto; border: 1px solid var(--border);
  border-radius: 10px; background: #131620;
}
table.trace { border-collapse: separate; border-spacing: 0; width: 100%; }
table.trace th, table.trace td {
  padding: 8px 14px; text-align: left; white-space: nowrap;
  border-bottom: 1px solid var(--border); font-size: 0.85rem;
}
table.trace thead th {
  position: sticky; top: 0; z-index: 2; background: var(--panel-alt);
  color: var(--text); font-weight: 600;
}
table.trace th.col-hop {
  position: sticky; left: 0; z-index: 1; background: var(--panel-alt);
  color: var(--muted); font-variant-numeric: tabular-nums; width: 1%;
}
table.trace thead th.col-hop { z-index: 3; }
table.trace tbody tr:hover td { background: rgba(56, 189, 248, 0.07); }
.hop-ip { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.loss {
  margin-left: 6px; color: var(--muted); font-variant-numeric: tabular-nums;
}
.loss--bad { color: var(--bad); }
.cell--missing { color: #4b5364; }
.empty { margin: 0; color: var(--muted); font-style: italic; }
.chart { min-height: 780px; }
.footnote { margin: 0; color: var(--muted); font-size: 0.78rem; }
::selection { background: rgba(56, 189, 248, 0.35); }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: #131620; }
::-webkit-scrollbar-thumb {
  background: #333a4d; border-radius: 6px; border: 2px solid #131620;
}
::-webkit-scrollbar-thumb:hover { background: #46506a; }
@media (max-width: 640px) {
  .page { padding: 20px 14px 40px; }
  .card__value { font-size: 1.6rem; }
}
"""

HTML_DOCUMENT = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Internet Status</title>
<style>{css}</style>
</head>
<body class="dark">
<div class="page">
<header class="masthead">
<h1>Internet Status</h1>
<p>Speed, latency, and packet loss collected by internet-troubleshooter.</p>
</header>
<main>
{summary}
{charts}
{traces}
</main>
<footer class="panel">
<p class="footnote">Dashed reference lines mark the thresholds this report
considers healthy: download &ge; {download}Mbps, upload &ge; {upload}Mbps,
latency &le; {latency}ms, packet loss &le; {loss}%. Dotted red lines mark runs
where a test did not complete.</p>
</footer>
</div>
</body>
</html>
"""


def to_human(results: Sequence[TestResult], io_target: TextIO = sys.stdout) -> None:
    speed_results = [result.speed_result for result in results]
    ping_results = [result.ping_result for result in results]
    print(
        "{}\n\n{}".format(
            SpeedResult.summarize(speed_results), PingResult.summarize(ping_results)
        ),
        file=io_target,
    )


def _import_plotly() -> Tuple[Any, Any]:
    """Import plotly on demand, reporting a helpful error when it is missing."""
    try:
        from plotly import graph_objs as go
        from plotly.subplots import make_subplots
    except ImportError as e:
        raise RuntimeError(
            "HTML output requires plotly, which is not installed. "
            "Install it with 'pip install internet-troubleshooter[html]' "
            "or 'pip install plotly'."
        ) from e
    return go, make_subplots


def _aligned_series(
    results: Sequence[TestResult],
) -> Tuple[
    List[datetime],
    List[Optional[float]],
    List[Optional[float]],
    List[Optional[float]],
    List[Optional[float]],
    List[Optional[float]],
]:
    """Every run's date, with one value list per metric aligned to it.

    All the traces share this x axis so that hovering a run reports each of its
    metrics together; a run that skipped or failed a test carries None, as does
    a ping that measured no round trip time.
    """
    dates = [result.get_date() for result in results]
    download: List[Optional[float]] = []
    upload: List[Optional[float]] = []
    latency: List[Optional[float]] = []
    ping_rtt: List[Optional[float]] = []
    packet_loss: List[Optional[float]] = []
    for result in results:
        speed = result.speed_result
        download.append(None if speed is None else speed.download)
        upload.append(None if speed is None else speed.upload)
        latency.append(None if speed is None else speed.latency)
        ping = result.ping_result
        ping_rtt.append(None if ping is None else ping.rtt_avg_ms)
        packet_loss.append(None if ping is None else ping.packet_loss)
    return dates, download, upload, latency, ping_rtt, packet_loss


def _measured(values: Sequence[Optional[float]]) -> List[float]:
    """The values that were actually recorded, dropping the missing ones."""
    return [value for value in values if value is not None]


def _format_threshold(value: float) -> str:
    """A threshold as written in labels, without a pointless trailing zero."""
    return "{:g}".format(value)


def _hover_value(value: Optional[float], unit: str) -> str:
    if value is None:
        return HOVER_MISSING
    return "{:.2f}{}".format(value, unit)


def _hover_texts(
    download: Sequence[Optional[float]],
    upload: Sequence[Optional[float]],
    latency: Sequence[Optional[float]],
    ping_rtt: Sequence[Optional[float]],
    packet_loss: Sequence[Optional[float]],
) -> List[str]:
    """One hover block per run, listing every metric for that run.

    A unified hover only covers the traces of the subplot being hovered, so
    every trace carries the whole block and any chart reports the full run.
    """
    return [
        (
            "Download: {}<br>Upload: {}<br>Latency: {}<br>"
            "Ping RTT: {}<br>Packet loss: {}"
        ).format(
            _hover_value(run_download, " Mbps"),
            _hover_value(run_upload, " Mbps"),
            _hover_value(run_latency, " ms"),
            _hover_value(run_rtt, " ms"),
            _hover_value(run_loss, "%"),
        )
        for run_download, run_upload, run_latency, run_rtt, run_loss in zip(
            download, upload, latency, ping_rtt, packet_loss
        )
    ]


def _packet_loss_axis_max(
    values: Sequence[Optional[float]],
    thresholds: RenderThresholds = DEFAULT_THRESHOLDS,
) -> float:
    """Upper bound for the packet loss axis, always showing the threshold."""
    measured = _measured(values)
    peak = max(measured) if measured else 0
    return min(
        100,
        max(
            MIN_PACKET_LOSS_RANGE,
            thresholds.packet_loss_pct * 2,
            peak * PACKET_LOSS_HEADROOM,
        ),
    )


def _add_threshold_line(
    fig: Any, value: float, label: str, row: int, position: str
) -> None:
    fig.add_hline(
        y=value,
        annotation_text=label,
        annotation_position=position,
        annotation_font_color=COLOR_MUTED,
        annotation_font_size=10,
        line_dash="dash",
        line_color=COLOR_GRID,
        line_width=1,
        row=row,
        col=1,
    )


def _add_metric_trace(
    fig: Any,
    go: Any,
    row: int,
    xs: Sequence[datetime],
    values: Sequence[Optional[float]],
    label: str,
    color: str,
    hover_texts: Optional[Sequence[str]],
    **extra: Any,
) -> None:
    """One metric line, hovering as the full run when hover_texts is given."""
    hover: Dict[str, Any]
    if hover_texts is None:
        hover = dict(hoverinfo="skip")
    else:
        hover = dict(text=hover_texts, hovertemplate="%{text}<extra></extra>")
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=values,
            name=label,
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=5),
            connectgaps=False,
            **hover,
            **extra,
        ),
        row=row,
        col=1,
    )


def _add_speed_chart(
    fig: Any,
    go: Any,
    xs: Sequence[datetime],
    download: Sequence[Optional[float]],
    upload: Sequence[Optional[float]],
    hover_texts: Sequence[str],
    thresholds: RenderThresholds,
) -> None:
    """Download and upload, sharing the Mbps axis on the first row."""
    _add_metric_trace(fig, go, 1, xs, download, "Download", COLOR_DOWNLOAD, hover_texts)
    # Download already carries the hover block for this row, and repeating it
    # for upload would print every metric twice in the unified hover.
    _add_metric_trace(fig, go, 1, xs, upload, "Upload", COLOR_UPLOAD, None)

    _add_threshold_line(
        fig,
        thresholds.download_mbps,
        "{}Mbps".format(_format_threshold(thresholds.download_mbps)),
        1,
        "top left",
    )
    _add_threshold_line(
        fig,
        thresholds.upload_mbps,
        "{}Mbps".format(_format_threshold(thresholds.upload_mbps)),
        1,
        "bottom left",
    )

    fig.update_yaxes(
        title_text="Internet Speed(Mbps)",
        rangemode="tozero",
        row=1,
        col=1,
    )


def _add_latency_chart(
    fig: Any,
    go: Any,
    xs: Sequence[datetime],
    latency: Sequence[Optional[float]],
    ping_rtt: Sequence[Optional[float]],
    hover_texts: Sequence[str],
    thresholds: RenderThresholds,
) -> None:
    """Latency on its own row, where the Mbps scale cannot flatten it.

    The average round trip time of the ping test shares the row, since it
    measures the same thing against a different target on the same ms scale.
    """
    _add_metric_trace(fig, go, 2, xs, latency, "Latency", COLOR_LATENCY, hover_texts)
    # Latency already carries the hover block for this row, and repeating it
    # would print every metric twice in the unified hover.
    _add_metric_trace(fig, go, 2, xs, ping_rtt, "Ping RTT", COLOR_PING, None)

    _add_threshold_line(
        fig,
        thresholds.latency_ms,
        "{}ms".format(_format_threshold(thresholds.latency_ms)),
        2,
        "top right",
    )

    fig.update_yaxes(title_text="Latency(ms)", rangemode="tozero", row=2, col=1)


def _add_packet_loss_chart(
    fig: Any,
    go: Any,
    xs: Sequence[datetime],
    packet_loss: Sequence[Optional[float]],
    hover_texts: Sequence[str],
    thresholds: RenderThresholds,
) -> None:
    """Packet loss against the primary ping target on the third row."""
    _add_metric_trace(
        fig,
        go,
        3,
        xs,
        packet_loss,
        "Packet Loss",
        COLOR_LOSS,
        hover_texts,
        fill="tozeroy",
        fillcolor="rgba(244, 114, 182, 0.12)",
    )

    _add_threshold_line(
        fig,
        thresholds.packet_loss_pct,
        "{}%".format(_format_threshold(thresholds.packet_loss_pct)),
        3,
        "top right",
    )

    fig.update_xaxes(title_text="Test Time", row=3, col=1)
    fig.update_yaxes(
        title_text="% Packet Loss",
        rangemode="tozero",
        range=[0, _packet_loss_axis_max(packet_loss, thresholds)],
        row=3,
        col=1,
    )


def _add_incomplete_run_markers(fig: Any, results: Sequence[TestResult]) -> None:
    """Mark runs where the ping or speed test failed to produce a value."""
    for result in results:
        if result.speed_result is not None and result.ping_result is not None:
            continue
        for row in (1, 2, 3):
            fig.add_vline(
                x=result.get_date(),
                line_dash="dot",
                line_color=COLOR_BAD,
                line_width=1,
                row=row,
                col=1,
            )


def _build_charts_figure(
    results: Sequence[TestResult], thresholds: RenderThresholds = DEFAULT_THRESHOLDS
) -> Any:
    """Dark themed figure with the speed, latency, and packet loss charts."""
    go, make_subplots = _import_plotly()

    dates, download, upload, latency, ping_rtt, packet_loss = _aligned_series(results)
    hover_texts = _hover_texts(download, upload, latency, ping_rtt, packet_loss)

    fig = make_subplots(
        shared_xaxes=True,
        rows=3,
        cols=1,
        row_heights=[0.4, 0.3, 0.3],
        vertical_spacing=0.06,
    )

    _add_speed_chart(fig, go, dates, download, upload, hover_texts, thresholds)
    _add_latency_chart(fig, go, dates, latency, ping_rtt, hover_texts, thresholds)
    _add_packet_loss_chart(fig, go, dates, packet_loss, hover_texts, thresholds)
    _add_incomplete_run_markers(fig, results)

    fig.update_layout(
        template="plotly_dark",
        height=CHART_HEIGHT,
        margin=dict(l=70, r=60, t=60, b=60),
        paper_bgcolor=COLOR_PANEL,
        plot_bgcolor=COLOR_PLOT,
        font=dict(color=COLOR_TEXT, size=12),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    fig.update_xaxes(gridcolor=COLOR_GRID, zerolinecolor=COLOR_GRID)
    fig.update_yaxes(gridcolor=COLOR_GRID, zerolinecolor=COLOR_GRID)

    return fig


def _metric_status(
    average: Optional[float], threshold: float, higher_is_better: bool
) -> str:
    """Whether the average sits on the healthy side of its threshold."""
    if average is None:
        return "empty"
    if higher_is_better:
        return "good" if average >= threshold else "bad"
    return "good" if average <= threshold else "bad"


def _metric_stats(
    label: str,
    unit: str,
    values: Sequence[float],
    threshold: float,
    higher_is_better: bool,
) -> Dict[str, Any]:
    average = safe_mean(values)
    return {
        "label": label,
        "unit": unit,
        "mean": average,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "samples": len(values),
        "threshold": threshold,
        "higher_is_better": higher_is_better,
        "status": _metric_status(average, threshold, higher_is_better),
    }


def _ping_target(results: Sequence[TestResult]) -> Optional[str]:
    """The ping target, when every run used the same one."""
    targets = {
        result.ping_result.ip for result in results if result.ping_result is not None
    }
    if len(targets) == 1:
        return targets.pop()
    return None


def _speed_context(results: Sequence[TestResult]) -> List[Tuple[str, str]]:
    """The speedtest details the runs agree on, as (label, value) pairs.

    Comes from the full JSON kept with each speed result, so it is empty for
    results logged before that was recorded. A detail the runs disagree on is
    dropped rather than reported as one value for the whole report.
    """
    contexts = [
        dict(result.speed_result.context())
        for result in results
        if result.speed_result is not None
    ]
    labels = list(dict.fromkeys(label for context in contexts for label in context))

    shared = []
    for label in labels:
        values = {context[label] for context in contexts if label in context}
        if len(values) == 1:
            shared.append((label, values.pop()))
    return shared


def _format_summary_stats(
    results: Sequence[TestResult], thresholds: RenderThresholds = DEFAULT_THRESHOLDS
) -> Dict[str, Any]:
    """Mean/min/max per metric plus run counts, for the summary cards.

    Expects results sorted by time stamp so the reported range is correct.
    """
    _, download, upload, latency, ping_rtt, packet_loss = _aligned_series(results)

    incomplete = [
        result
        for result in results
        if result.speed_result is None or result.ping_result is None
    ]

    return {
        "metrics": [
            _metric_stats(
                "Download", "Mbps", _measured(download), thresholds.download_mbps, True
            ),
            _metric_stats(
                "Upload", "Mbps", _measured(upload), thresholds.upload_mbps, True
            ),
            _metric_stats(
                "Latency", "ms", _measured(latency), thresholds.latency_ms, False
            ),
            # The ping target is not the speedtest server, but a healthy round
            # trip to either one is the same figure, so they share a threshold.
            _metric_stats(
                "Ping RTT", "ms", _measured(ping_rtt), thresholds.latency_ms, False
            ),
            _metric_stats(
                "Packet Loss",
                "%",
                _measured(packet_loss),
                thresholds.packet_loss_pct,
                False,
            ),
        ],
        "runs": len(results),
        "incomplete": len(incomplete),
        "ping_target": _ping_target(results),
        "speed_context": _speed_context(results),
        "first_run": _format_run_time(results[0]) if results else None,
        "last_run": _format_run_time(results[-1]) if results else None,
    }


def _format_run_time(result: TestResult) -> str:
    return result.get_date().strftime(DATE_FORMAT)


def _format_measurement(value: Optional[float], unit: str) -> str:
    if value is None:
        return MISSING_VALUE
    return "{:.2f}{}".format(value, unit)


def _chips_html(fragments: Iterable[str]) -> str:
    """Pill shaped labels; fragments must already be HTML safe."""
    chips = "".join(
        '<span class="chip">{}</span>'.format(fragment) for fragment in fragments
    )
    return '<div class="chips">{}</div>'.format(chips)


def _panel_html(panel_id: str, title: str, aside_html: str, body_html: str) -> str:
    return (
        '<section class="panel" id="{panel_id}">'
        '<div class="panel__header"><h2>{title}</h2>{aside}</div>'
        "{body}"
        "</section>"
    ).format(panel_id=panel_id, title=title, aside=aside_html, body=body_html)


def _metric_card_html(metric: Mapping[str, Any]) -> str:
    comparison = "&ge;" if metric["higher_is_better"] else "&le;"
    return (
        '<article class="card card--{status}">'
        '<h3 class="card__label">{label}</h3>'
        '<p class="card__value">{mean}<span class="card__unit">{unit}</span></p>'
        '<dl class="card__stats">'
        "<div><dt>Min</dt><dd>{minimum}</dd></div>"
        "<div><dt>Max</dt><dd>{maximum}</dd></div>"
        "</dl>"
        '<p class="card__note">Target {comparison} {threshold}{unit}</p>'
        "</article>"
    ).format(
        status=metric["status"],
        label=escape(metric["label"]),
        mean=_format_measurement(metric["mean"], ""),
        unit=escape(metric["unit"]),
        minimum=_format_measurement(metric["minimum"], metric["unit"]),
        maximum=_format_measurement(metric["maximum"], metric["unit"]),
        comparison=comparison,
        threshold=_format_threshold(metric["threshold"]),
    )


def _summary_chips(summary: Mapping[str, Any]) -> List[str]:
    fragments = ["{} run(s)".format(summary["runs"])]
    if summary["ping_target"] is not None:
        fragments.append("Target {}".format(escape(summary["ping_target"])))
    fragments.extend(
        "{} {}".format(escape(label), escape(value))
        for label, value in summary["speed_context"]
    )
    if summary["incomplete"]:
        fragments.append("{} incomplete run(s)".format(summary["incomplete"]))
    if summary["first_run"] == summary["last_run"]:
        fragments.append(summary["first_run"] or "No runs yet")
    else:
        fragments.append(
            "{} &rarr; {}".format(summary["first_run"], summary["last_run"])
        )
    return fragments


def _build_summary_html(summary: Mapping[str, Any]) -> str:
    """Metric cards showing the mean, min, and max of every measurement."""
    if not summary["runs"]:
        body = '<p class="empty">No results to summarize yet.</p>'
    else:
        body = '<div class="cards">{}</div>'.format(
            "".join(_metric_card_html(metric) for metric in summary["metrics"])
        )
    return _panel_html("summary", "Summary", _chips_html(_summary_chips(summary)), body)


def _trace_rows(
    trace_results: Sequence[TestResult],
) -> List[Tuple[int, List[Optional[PingResult]]]]:
    """One row per hop index, holding the ping for each traced run.

    Callers pass only the runs that recorded a trace.
    """
    hop_lists = [
        cast(TraceResult, result.trace_result).ping_results for result in trace_results
    ]
    hop_count = max(len(hops) for hops in hop_lists)
    rows = []
    for index in range(hop_count):
        pings = [hops[index] if index < len(hops) else None for hops in hop_lists]
        rows.append((index + 1, pings))
    return rows


def _trace_cell_html(
    ping: Optional[PingResult], thresholds: RenderThresholds = DEFAULT_THRESHOLDS
) -> str:
    if ping is None:
        return '<td class="cell--missing">{}</td>'.format(MISSING_VALUE)
    bad = ping.packet_loss > thresholds.packet_loss_pct
    loss_class = "loss loss--bad" if bad else "loss"
    # The space between the spans keeps the cell readable once it is copied,
    # where the margin between them is lost.
    return (
        '<td><span class="hop-ip">{ip}</span> '
        '<span class="{loss_class}">{loss:.2f}%</span></td>'
    ).format(
        ip=escape(str(ping.ip)),
        loss_class=loss_class,
        loss=ping.packet_loss,
    )


def _trace_table_html(
    trace_results: Sequence[TestResult],
    thresholds: RenderThresholds = DEFAULT_THRESHOLDS,
) -> str:
    header = "".join(
        '<th scope="col">{}</th>'.format(escape(_format_run_time(result)))
        for result in trace_results
    )
    rows = "".join(
        '<tr><th scope="row" class="col-hop">{}</th>{}</tr>'.format(
            hop_number,
            "".join(_trace_cell_html(ping, thresholds) for ping in pings),
        )
        for hop_number, pings in _trace_rows(trace_results)
    )
    return (
        '<div class="table-scroll">'
        '<table class="trace">'
        '<thead><tr><th scope="col" class="col-hop">Hop</th>{header}</tr></thead>'
        "<tbody>{rows}</tbody>"
        "</table>"
        "</div>"
    ).format(header=header, rows=rows)


def _build_trace_tables_html(
    results: Sequence[TestResult], thresholds: RenderThresholds = DEFAULT_THRESHOLDS
) -> str:
    """Scrollable, selectable table of traceroute hops, one column per run."""
    trace_results = [result for result in results if result.trace_result is not None]

    if not trace_results:
        return _panel_html(
            "traces",
            "Traceroute Hops",
            _chips_html(["No traces recorded"]),
            '<p class="empty">Traceroutes only run when packet loss is high, '
            "and none were recorded for these results.</p>",
        )

    rows = _trace_rows(trace_results)
    chips = [
        "{} traced run(s)".format(len(trace_results)),
        "{} hop(s) deep".format(len(rows)),
    ]
    return _panel_html(
        "traces",
        "Traceroute Hops",
        _chips_html(chips),
        _trace_table_html(trace_results, thresholds),
    )


def _build_charts_html(
    results: Sequence[TestResult],
    thresholds: RenderThresholds = DEFAULT_THRESHOLDS,
    embed_plotly: bool = False,
) -> str:
    """The charts, loading plotly.js from the CDN or inlining it when asked."""
    fig = _build_charts_figure(results, thresholds)
    return cast(
        str,
        fig.to_html(
            full_html=False,
            include_plotlyjs=True if embed_plotly else "cdn",
            config={"displayModeBar": True, "responsive": True},
        ),
    )


def _assemble_html_document(
    charts_html: str,
    summary_html: str,
    trace_html: str,
    thresholds: RenderThresholds = DEFAULT_THRESHOLDS,
) -> str:
    charts_panel = _panel_html(
        "charts",
        "Performance Over Time",
        _chips_html(["Drag to zoom", "Double click to reset"]),
        '<div class="chart">{}</div>'.format(charts_html),
    )
    return HTML_DOCUMENT.format(
        css=PAGE_CSS,
        summary=summary_html,
        charts=charts_panel,
        traces=trace_html,
        download=_format_threshold(thresholds.download_mbps),
        upload=_format_threshold(thresholds.upload_mbps),
        latency=_format_threshold(thresholds.latency_ms),
        loss=_format_threshold(thresholds.packet_loss_pct),
    )


def _write_html(document: str, io_target: HtmlTarget) -> None:
    if hasattr(io_target, "write"):
        io_target.write(document)
        return
    with open(io_target, "w", encoding="utf-8") as target:
        target.write(document)


def to_html(
    results: Sequence[TestResult],
    io_target: HtmlTarget = sys.stdout,
    thresholds: Optional[RenderThresholds] = None,
    embed_plotly: bool = False,
) -> None:
    """Write the HTML report, inlining plotly.js when embed_plotly is set.

    The inlined report is several megabytes larger but needs no network access
    to open, where the default only carries a script tag for the plotly CDN.
    """
    thresholds = DEFAULT_THRESHOLDS if thresholds is None else thresholds
    results = sorted(results, key=lambda x: x.time_stamp)

    document = _assemble_html_document(
        _build_charts_html(results, thresholds, embed_plotly),
        _build_summary_html(_format_summary_stats(results, thresholds)),
        _build_trace_tables_html(results, thresholds),
        thresholds,
    )

    _write_html(document, io_target)
