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
    ping_result: PingResult
    trace_result: TraceResult
    speed_result: SpeedResult
    time_stamp: float = field(default_factory=time)

    def human_readable(self, io_target=sys.stdout):
        if self.ping_result is not None:
            print(
                "Packet Loss: {:.2f}%".format(self.ping_result.packet_loss),
                file=io_target,
            )

        if self.trace_result is not None:
            for hop_result in self.trace_result.ping_results:
                if hop_result is None:
                    continue
                print(
                    "{:.2f}% {}".format(hop_result.packet_loss, hop_result.ip),
                    file=io_target,
                )

        if self.speed_result is not None:
            print(
                self.speed_result,
                file=io_target,
            )

    def to_dict(self):
        return {
            "ping_result": (
                None if self.ping_result is None else self.ping_result.to_dict()
            ),
            "trace_result": (
                None if self.trace_result is None else self.trace_result.to_dict()
            ),
            "speed_result": (
                None if self.speed_result is None else self.speed_result.to_dict()
            ),
            "time_stamp": self.time_stamp,
        }

    @classmethod
    def from_dict(cls, data):
        ping_result = data.get("ping_result")
        trace_result = data.get("trace_result")
        speed_result = data.get("speed_result")
        time_stamp = data.get("time_stamp")

        return cls(
            ping_result=(
                None if ping_result is None else PingResult.from_dict(ping_result)
            ),
            trace_result=(
                None if trace_result is None else TraceResult.from_dict(trace_result)
            ),
            speed_result=(
                None if speed_result is None else SpeedResult.from_dict(speed_result)
            ),
            **({} if time_stamp is None else {"time_stamp": float(time_stamp)}),
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
        return datetime.fromtimestamp(self.time_stamp)

    @staticmethod
    def to_human(results, io_target=sys.stdout):
        speed_results = [result.speed_result for result in results]
        ping_results = [result.ping_result for result in results]
        print(
            "{}\n\n{}".format(
                SpeedResult.summarize(speed_results), PingResult.summarize(ping_results)
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

        results = sorted(results, key=lambda x: x.time_stamp)

        xs = [
            result.get_date() for result in results if result.speed_result is not None
        ]

        fig = make_subplots(
            shared_xaxes=True,
            rows=3,
            cols=1,
            specs=[[{"secondary_y": True}], [dict()], [{"type": "domain"}]],
        )

        download = [
            result.speed_result.download
            for result in results
            if result.speed_result is not None
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
            result.speed_result.upload
            for result in results
            if result.speed_result is not None
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
            result.speed_result.latency
            for result in results
            if result.speed_result is not None
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

        xs = [result.get_date() for result in results if result.ping_result is not None]

        packet_loss = [
            result.ping_result.packet_loss
            for result in results
            if result.ping_result is not None
        ]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=packet_loss,
                name=trace_name("Packet Loss", packet_loss),
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
            if result.speed_result is None or result.ping_result is None:
                fig.add_vline(
                    x=result.get_date(), line_dash="dot", line_color="red", row=1, col=1
                )
                fig.add_vline(
                    x=result.get_date(), line_dash="dot", line_color="red", row=2, col=1
                )

        trace_results = [
            result for result in results if result.trace_result is not None
        ]

        fig.add_trace(
            go.Table(
                header=dict(
                    values=[result.get_date() for result in trace_results],
                    font=dict(size=10),
                    align="left",
                ),
                cells=dict(
                    values=[
                        [str(ping) for ping in result.trace_result.ping_results]
                        for result in trace_results
                    ],
                    align="left",
                ),
            ),
            row=3,
            col=1,
        )

        fig.update_layout(title_text="Internet Status")

        fig.write_html(io_target, full_html=True, include_plotlyjs="cdn")
