import asyncio
from pathlib import Path
from textual.widgets import Log, Static
from textual.app import ComposeResult


PROCFILE = Path(__file__).resolve().absolute().parents[2] / "Procfile"


class HonchoLogWidget(Static):
    def __init__(self, procfile: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.procfile = procfile or str(PROCFILE)
        self.process = None
        self.log_task = None

    def compose(self) -> ComposeResult:
        yield Log(id="honcho-log", highlight=True)

    async def on_mount(self) -> None:
        self._log = self.query_one(Log)

        cmd = ["honcho", "start"]
        if self.procfile:
            cmd += ["-f", self.procfile]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        self.log_task = asyncio.create_task(self._read_logs())

    async def _read_logs(self):
        while True:
            line = await self.process.stdout.readline()
            if not line:
                break
            self._log.write_line(line.decode().rstrip())

    async def _shutdown_honcho(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception:
                pass
        if self.log_task:
            self.log_task.cancel()
            try:
                await self.log_task
            except asyncio.CancelledError:
                pass
