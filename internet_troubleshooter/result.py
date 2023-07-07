import sys
from time import time
from datetime import datetime
from dataclasses import dataclass, field
import yaml
from yaml.loader import UnsafeLoader
from statistics import mean, variance

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult
from internet_troubleshooter.speed_test import SpeedResult


@dataclass
class TestResult:
    pingResult: PingResult = field()
    traceResult: TraceResult = field()
    speedResult: SpeedResult = field()
    timeStamp: float = time()

    def human_readable(self, io_target=sys.stdout):
        if self.pingResult is not None:
            print(
                "Packet Loss: {:.2f}%".format(self.pingResult.packetLoss),
                file=io_target,
            )

        if self.traceResult is not None:
            for trace_result in self.traceResult.pingResults:
                print(
                    "{:.2f}% {}".format(trace_result.packetLoss, trace_result.ip), file=io_target
                )

        if self.speedResult is not None:
            print(
                self.speedResult,
                file=io_target,
            )

    def to_yaml(self):
        return yaml.dump(self)

    def load_results(yaml_filename):
        with open(yaml_filename) as f:
            return yaml.load_all(f.read(), Loader=UnsafeLoader)

    def get_date(self):
        return datetime.fromtimestamp(self.timeStamp)

    def to_human(results, io_target=sys.stdout):
        speedResults = [
            result.speedResult
            for result in results
        ]
        pingResults = [
            result.pingResult
            for result in results
        ]
        print(
            "{}\n\n{}".format(SpeedResult.summarize(speedResults), PingResult.summarize(pingResults)),
            file=io_target,
        )

    def to_html(results, io_target=sys.stdout):
        from plotly import graph_objs as go
        from plotly.subplots import make_subplots

        results.sort(key=lambda x: x.timeStamp)

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
            go.Scatter(
                x=xs, y=download, name="Download (avg: {:.2f})".format(mean(download))
            ),
            secondary_y=False,
            row=1,
            col=1,
        )
        fig.add_hline(
            y=50,
            annotation_text="50Mbps",
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
            go.Scatter(
                x=xs, y=upload, name="Upload (avg: {:.2f})".format(mean(upload))
            ),
            secondary_y=False,
            row=1,
            col=1,
        )
        fig.add_hline(
            y=15,
            annotation_text="15Mbps",
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
            go.Scatter(
                x=xs, y=latency, name="Latency (avg: {:.2f})".format(mean(latency))
            ),
            secondary_y=True,
            row=1,
            col=1,
        )
        fig.add_hline(y=20, line_dash="dash", secondary_y=True, row=1, col=1)

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
                name="Packet Loss (avg: {:.2f})".format(mean(packetLoss)),
            ),
            row=2,
            col=1,
        )
        fig.add_hline(
            y=3,
            annotation_text="3%",
            annotation_position="top right",
            line_dash="dash",
            row=2,
            col=1,
        )

        fig.update_xaxes(title_text="Test Time", row=2, col=1)

        fig.update_yaxes(title_text="% Packet Loss", rangemode="tozero", row=2, col=1)

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
