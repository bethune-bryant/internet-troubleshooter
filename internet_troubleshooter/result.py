import sys
from time import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
import yaml

from internet_troubleshooter.ping_test import PingResult
from internet_troubleshooter.trace_test import TraceResult
from internet_troubleshooter.speed_test import SpeedResult


@dataclass
class TestResult:
    ping_result: Optional[PingResult]
    trace_result: Optional[TraceResult]
    speed_result: Optional[SpeedResult]
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
