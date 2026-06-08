import time
from unittest.mock import patch, MagicMock

import pytest

from backend.memory_monitor import MemoryMonitor, MemoryThresholdExceeded


class TestMemoryThresholdExceeded:
    def test_is_exception(self):
        assert issubclass(MemoryThresholdExceeded, Exception)

    def test_default_message(self):
        exc = MemoryThresholdExceeded()
        assert str(exc) == ""

    def test_custom_message(self):
        exc = MemoryThresholdExceeded("custom error")
        assert str(exc) == "custom error"


class TestMemoryMonitor:
    def test_context_manager(self):
        with MemoryMonitor(limit_mb=999999) as mon:
            assert not mon.exceeded
            mon.check()

    def test_check_raises_when_exceeded(self):
        mon = MemoryMonitor(limit_mb=999999)
        mon.exceeded = True
        with pytest.raises(MemoryThresholdExceeded):
            mon.check()

    def test_check_no_error_when_not_exceeded(self):
        mon = MemoryMonitor(limit_mb=999999)
        mon.exceeded = False
        mon.check()

    @patch("psutil.Process")
    def test_monitor_triggers_on_high_memory(self, mock_process):
        mock_instance = MagicMock()
        mock_instance.memory_info.return_value.rss = 999999 * 1024 * 1024
        mock_process.return_value = mock_instance

        mon = MemoryMonitor(limit_mb=600, poll_interval=0.05)
        with mon:
            time.sleep(0.2)
            assert mon.exceeded

    @patch("psutil.Process")
    def test_monitor_does_not_trigger_on_low_memory(self, mock_process):
        mock_instance = MagicMock()
        mock_instance.memory_info.return_value.rss = 50 * 1024 * 1024
        mock_process.return_value = mock_instance

        mon = MemoryMonitor(limit_mb=600, poll_interval=0.05)
        with mon:
            time.sleep(0.2)
            assert not mon.exceeded

    @patch("psutil.Process")
    def test_monitor_stops_on_context_exit(self, mock_process):
        mock_instance = MagicMock()
        mock_instance.memory_info.return_value.rss = 50 * 1024 * 1024
        mock_process.return_value = mock_instance

        mon = MemoryMonitor(limit_mb=600, poll_interval=0.05)
        with mon:
            pass
        assert not mon._running

    def test_default_limits(self):
        mon = MemoryMonitor()
        assert mon.limit == 600 * 1024 * 1024
        assert mon.interval == 0.5
