import sys
from time import time
from datetime import datetime
from dataclasses import dataclass, field
import yaml

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult
from internet_troubleshooter.speed_test import SpeedResult
from internet_troubleshooter.utils import safe_mean

# Reference lines drawn on the HTML plots, marking the thresholds below which a
# connection is considered to be underperforming.
PLOT_DOWNLOAD_MBPS = 50
PLOT_UPLOAD_MBPS = 15
PLOT_LATENCY_MS = 20
PLOT_PACKET_LOSS_PCT = 3


def trace_name(label, values):
    average = safe_mean(values)
    if average is None:
        return label
    return "{} (avg: {:.2f})".format(label, average)


@dataclass
class TestResult:
    pingResult: PingResult
    traceResult: TraceResult
    speedResult: SpeedResult
    timeStamp: float = field(default_factory=time)

    def human_readable(self, io_target=sys.stdout):
        if self.pingResult is not None:
            print(
                "Packet Loss: {:.2f}%".format(self.pingResult.packetLoss),
                file=io_target,
            )

        if self.traceResult is not None:
            for trace_result in self.traceResult.pingResults:
                if trace_result is None:
                    continue
                print(
                    "{:.2f}% {}".format(trace_result.packetLoss, trace_result.ip),
                    file=io_target,
                )

        if self.speedResult is not None:
            print(
                self.speedResult,
                file=io_target,
            )

    def to_dict(self):
        return {
            "pingResult": (
                None if self.pingResult is None else self.pingResult.to_dict()
            ),
            "traceResult": (
                None if self.traceResult is None else self.traceResult.to_dict()
            ),
            "speedResult": (
                None if self.speedResult is None else self.speedResult.to_dict()
            ),
            "timeStamp": self.timeStamp,
        }

    @classmethod
    def from_dict(cls, data):
        pingResult = data.get("pingResult")
        traceResult = data.get("traceResult")
        speedResult = data.get("speedResult")
        timeStamp = data.get("timeStamp")

        return cls(
            pingResult=None if pingResult is None else PingResult.from_dict(pingResult),
            traceResult=(
                None if traceResult is None else TraceResult.from_dict(traceResult)
            ),
            speedResult=(
                None if speedResult is None else SpeedResult.from_dict(speedResult)
            ),
            **({} if timeStamp is None else {"timeStamp": float(timeStamp)}),
        )

    def to_yaml(self):
        return yaml.safe_dump(self.to_dict(), default_flow_style=False)

    @staticmethod
    def load_yaml(content):
        """Parse the contents of a results file into TestResult objects."""
        documents = yaml.safe_load_all(content)

        return [
            TestResult.from_dict(document)
            for document in documents
            if isinstance(document, dict)
        ]

    @staticmethod
    def load_results(yaml_filename):
        with open(yaml_filename, encoding="utf-8") as f:
            return TestResult.load_yaml(f.read())

    def get_date(self):
        return datetime.fromtimestamp(self.timeStamp)

    @staticmethod
    def to_human(results, io_target=sys.stdout):
        speedResults = [result.speedResult for result in results]
        pingResults = [result.pingResult for result in results]
        print(
            "{}\n\n{}".format(
                SpeedResult.summarize(speedResults), PingResult.summarize(pingResults)
            ),
            file=io_target,
        )

    @staticmethod
    def to_html(results, io_target=sys.stdout):
        try:
            from plotly import graph_objs as go
            from plotly.subplots import make_subplots
        except ImportError as e:
            raise RuntimeError(
                "HTML output requires plotly, which is not installed. "
                "Install it with 'pip install internet-troubleshooter[html]' "
                "or 'pip install plotly'."
            ) from e

        results = sorted(results, key=lambda x: x.timeStamp)

        xs = [result.get_date() for result in results if result.speedResult is not None]

        fig = make_subplots(
            shared_xaxes=True,
            rows=3,
            cols=1,
            specs=[[{"secondary_y": True}], [dict()], [{"type": "domain"}]],
        )

        download = [
            result.speedResult.download
            for result in results
            if result.speedResult is not None
        ]
        fig.add_trace(
            go.Scatter(x=xs, y=download, name=trace_name("Download", download)),
            secondary_y=False,
            row=1,
            col=1,
        )
        fig.add_hline(
            y=PLOT_DOWNLOAD_MBPS,
            annotation_text="{}Mbps".format(PLOT_DOWNLOAD_MBPS),
            annotation_position="top left",
            line_dash="dash",
            secondary_y=False,
            row=1,
            col=1,
        )

        upload = [
            result.speedResult.upload
            for result in results
            if result.speedResult is not None
        ]
        fig.add_trace(
            go.Scatter(x=xs, y=upload, name=trace_name("Upload", upload)),
            secondary_y=False,
            row=1,
            col=1,
        )
        fig.add_hline(
            y=PLOT_UPLOAD_MBPS,
            annotation_text="{}Mbps".format(PLOT_UPLOAD_MBPS),
            annotation_position="top left",
            line_dash="dash",
            secondary_y=False,
            row=1,
            col=1,
        )

        latency = [
            result.speedResult.latency
            for result in results
            if result.speedResult is not None
        ]
        fig.add_trace(
            go.Scatter(x=xs, y=latency, name=trace_name("Latency", latency)),
            secondary_y=True,
            row=1,
            col=1,
        )
        fig.add_hline(
            y=PLOT_LATENCY_MS, line_dash="dash", secondary_y=True, row=1, col=1
        )

        fig.update_yaxes(
            title_text="Internet Speed(Mbps)",
            rangemode="tozero",
            secondary_y=False,
            row=1,
            col=1,
        )
        fig.update_yaxes(
            title_text="Latency(ms)", rangemode="tozero", secondary_y=True, row=1, col=1
        )

        xs = [result.get_date() for result in results if result.pingResult is not None]

        packetLoss = [
            result.pingResult.packetLoss
            for result in results
            if result.pingResult is not None
        ]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=packetLoss,
                name=trace_name("Packet Loss", packetLoss),
            ),
            row=2,
            col=1,
        )
        fig.add_hline(
            y=PLOT_PACKET_LOSS_PCT,
            annotation_text="{}%".format(PLOT_PACKET_LOSS_PCT),
            annotation_position="top right",
            line_dash="dash",
            row=2,
            col=1,
        )

        fig.update_xaxes(title_text="Test Time", row=2, col=1)

        fig.update_yaxes(
            title_text="% Packet Loss",
            rangemode="tozero",
            range=[0, 100],
            row=2,
            col=1,
        )

        for result in results:
            if result.speedResult is None or result.pingResult is None:
                fig.add_vline(
                    x=result.get_date(), line_dash="dot", line_color="red", row=1, col=1
                )
                fig.add_vline(
                    x=result.get_date(), line_dash="dot", line_color="red", row=2, col=1
                )

        traceResults = [result for result in results if result.traceResult is not None]

        fig.add_trace(
            go.Table(
                header=dict(
                    values=[result.get_date() for result in traceResults],
                    font=dict(size=10),
                    align="left",
                ),
                cells=dict(
                    values=[
                        [str(ping) for ping in result.traceResult.pingResults]
                        for result in traceResults
                    ],
                    align="left",
                ),
            ),
            row=3,
            col=1,
        )

        fig.update_layout(title_text="Internet Status")

        fig.write_html(io_target, full_html=True, include_plotlyjs="cdn")
