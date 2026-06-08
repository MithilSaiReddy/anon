import logging
import sys
from datetime import date
from logging import Handler, LogRecord
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"


class DailyLogHandler(Handler):
    """Writes to logs/{env}/YYYY-MM-DD.log, auto-creates new file at midnight."""

    def __init__(self, log_dir: Path):
        super().__init__()
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_date: date | None = None
        self._handler: Handler | None = None

    def _rotate(self) -> Handler:
        today = date.today()
        if today != self._current_date:
            if self._handler is not None:
                self._handler.close()
            log_file = self.log_dir / f"{today.isoformat()}.log"
            self._handler = logging.FileHandler(log_file, encoding="utf-8")
            self._handler.setFormatter(self.formatter)
            self._current_date = today
        return self._handler

    def emit(self, record: LogRecord) -> None:
        handler = self._rotate()
        handler.emit(record)


class _ExcludeLoggerFilter(logging.Filter):
    """Filters out records from specified loggers to avoid double-logging."""

    def __init__(self, *exclude_names: str):
        super().__init__()
        self.exclude_names = exclude_names

    def filter(self, record: LogRecord) -> bool:
        return not any(record.name.startswith(n) for n in self.exclude_names)


def setup_logging(app_env: str = "dev") -> None:
    log_dir = LOG_DIR / app_env
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = DailyLogHandler(log_dir)
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if app_env == "dev" else logging.INFO)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    root.addHandler(file_handler)

    if app_env == "dev":
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        console.addFilter(_ExcludeLoggerFilter("uvicorn.access"))
        root.addHandler(console)
