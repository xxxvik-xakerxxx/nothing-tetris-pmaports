"""Opt-in diagnostic tracing around a separately reviewed GNSS operation."""
import os
from pathlib import Path


FUNCTIONS = frozenset((
    "gps_dl_hal_mcub_flag_handler",
    "gps_dl_hw_clear_mcub_d2a_flag",
    "gps_dsp_fsm",
    "gps_dsp_state_change_to",
    "gps_dl_link_set_ready_to_write",
    "gps_dl_link_start_tx_dma_if_has_data",
))


class TraceError(RuntimeError):
    pass


class TraceFiles:
    root = Path("/sys/kernel/tracing")

    def read(self, path, limit=2 * 1024 * 1024):
        with (self.root / path).open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise TraceError("trace read exceeds bound")
        return data.decode("ascii")

    def write(self, path, text):
        with (self.root / path).open("w", encoding="ascii") as stream:
            if stream.write(text) != len(text):
                raise TraceError("short trace-control write")

    def mkdir(self, path):
        (self.root / path).mkdir()

    def rmdir(self, path):
        (self.root / path).rmdir()

    def stats(self, instance):
        paths = sorted((self.root / instance / "per_cpu").glob("cpu*/stats"))
        if not paths or len(paths) > 256:
            raise TraceError("invalid trace CPU inventory")
        return {str(p.relative_to(self.root)): self.read(str(p.relative_to(self.root)), 8192)
                for p in paths}


class StopTrace:
    def __init__(self, files=None):
        self.files = files if files is not None else TraceFiles()
        self.instance = f"instances/tetris-gps-stop-{os.getpid()}"
        self.created = False

    def control(self, name, value):
        self.files.write(f"{self.instance}/{name}", value + "\n")

    def start(self):
        if "function_graph" not in self.files.read("available_tracers").split():
            raise TraceError("function graph tracing unavailable")
        available = {line.split()[0] for line in
                     self.files.read("available_filter_functions").splitlines() if line.strip()}
        if not FUNCTIONS <= available:
            raise TraceError("required GNSS functions are not traceable")
        self.files.mkdir(self.instance)  # Exclusive: never take another observer's instance.
        self.created = True
        try:
            self.control("tracing_on", "0")
            self.control("buffer_size_kb", "64")
            self.control("set_ftrace_filter", "\n".join(sorted(FUNCTIONS)))
            selected = {line.split()[0] for line in
                        self.files.read(f"{self.instance}/set_ftrace_filter").splitlines()
                        if line.strip()}
            if selected != FUNCTIONS:
                raise TraceError("trace filter does not match the six reviewed functions")
            self.control("trace_clock", "mono")
            for option in ("funcgraph-abstime", "funcgraph-proc", "funcgraph-duration", "sleep-time"):
                self.control(f"options/{option}", "1")
            self.control("current_tracer", "function_graph")
            self.control("tracing_on", "1")
        except BaseException:
            self.close()
            raise

    def snapshot(self):
        self.control("tracing_on", "0")
        trace = self.files.read(f"{self.instance}/trace")
        stats = self.files.stats(self.instance)
        return trace, stats

    @staticmethod
    def validate_stats(stats):
        for contents in stats.values():
            values = dict(line.split(":", 1) for line in contents.splitlines() if ":" in line)
            for name in ("overrun", "commit overrun", "dropped events"):
                if name not in values or int(values[name].strip()) != 0:
                    raise TraceError("trace lost events or has unrecognized statistics")

    def close(self):
        if self.created:
            try:
                self.control("tracing_on", "0")
                self.control("current_tracer", "nop")
            finally:
                self.files.rmdir(self.instance)
                self.created = False


def run_traced(operation, files=None):
    """Caller owns hardware preconditions/recovery; no operation is supplied here.

    Start failure never invokes operation. Capture and remove only our instance
    even when the operation raises. Return failures explicitly, never retry.
    """
    session = StopTrace(files)
    session.start()
    result = {"operation_error": None, "trace_error": None, "cleanup_error": None,
              "trace": None, "stats": None, "instance": session.instance, "ok": False}
    try:
        try:
            operation()
        except BaseException as error:
            result["operation_error"] = f"{type(error).__name__}: {error}"
        try:
            result["trace"], result["stats"] = session.snapshot()
            session.validate_stats(result["stats"])
        except Exception as error:
            result["trace_error"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            session.close()
        except Exception as error:
            result["cleanup_error"] = f"{type(error).__name__}: {error}"
    result["ok"] = all(result[name] is None for name in
                       ("operation_error", "trace_error", "cleanup_error"))
    return result
