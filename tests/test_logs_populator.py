import pytest  # noqa: F401
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from pipen_poplog import LogsPopulator


class TestLogsPopulator:
    """Test cases for the LogsPopulator class."""

    def test_init_with_string_path(self):
        """Test initialization with a string path."""
        populator = LogsPopulator("/path/to/logfile.log")
        assert populator.logfile.name == "logfile.log"
        assert populator.handler is None
        assert populator.residue == b""
        assert populator.counter == 0

    def test_init_with_path_object(self):
        """Test initialization with a Path object."""
        path = Path("/path/to/logfile.log")
        populator = LogsPopulator(path)
        assert populator.logfile == path
        assert populator.handler is None
        assert populator.residue == b""
        assert populator.counter == 0

    def test_init_with_none(self):
        """Test initialization with None."""
        populator = LogsPopulator(None)
        assert populator.logfile is None
        assert populator.handler is None
        assert populator.residue == b""
        assert populator.counter == 0

    async def test_populate_nonexistent_file(self):
        """Test populate method when log file doesn't exist."""
        mock_logfile = Mock()
        mock_logfile.a_exists = AsyncMock(return_value=False)

        populator = LogsPopulator()
        populator.logfile = mock_logfile

        result = await populator.populate()
        assert result == []
        assert populator.counter == 0

    async def test_populate_empty_file(self):
        """Test populate method with empty file."""
        mock_logfile = Mock()

        mock_logfile.a_exists = AsyncMock(return_value=True)
        mock_handler = Mock()
        mock_handler.read = AsyncMock(return_value=b"")
        mock_handler.__aenter__ = AsyncMock(return_value=mock_handler)
        mock_logfile.a_open = Mock(return_value=mock_handler)

        populator = LogsPopulator()
        populator.logfile = mock_logfile

        result = await populator.populate()
        assert result == []
        populator.increment_counter()
        assert populator.counter == 1
        assert populator.residue == b""

    async def test_populate_complete_lines(self):
        """Test populate method with complete lines ending with newline."""
        content = b"line1\nline2\nline3\n"
        mock_logfile = Mock()
        mock_logfile.a_exists = AsyncMock(return_value=True)
        mock_handler = Mock()
        mock_handler.read = AsyncMock(return_value=content)
        mock_handler.__aenter__ = AsyncMock(return_value=mock_handler)
        mock_logfile.a_open = Mock(return_value=mock_handler)

        populator = LogsPopulator()
        populator.logfile = mock_logfile

        result = await populator.populate()
        assert result == ["line1", "line2", "line3"]
        populator.increment_counter()
        assert populator.counter == 1
        assert populator.residue == b""

    async def test_populate_incomplete_last_line(self):
        """Test populate method with incomplete last line (no trailing newline)."""
        content = b"line1\nline2\nincomplete"
        mock_logfile = Mock()
        mock_logfile.a_exists = AsyncMock(return_value=True)
        mock_handler = Mock()
        mock_handler.read = AsyncMock(return_value=content)
        mock_handler.__aenter__ = AsyncMock(return_value=mock_handler)
        mock_logfile.a_open = Mock(return_value=mock_handler)

        populator = LogsPopulator()
        populator.logfile = mock_logfile

        result = await populator.populate()
        assert result == ["line1", "line2"]
        populator.increment_counter()
        assert populator.counter == 1
        assert populator.residue == b"incomplete"

    async def test_populate_with_residue_from_previous_read(self):
        """Test populate method using residue from previous read."""
        mock_logfile = Mock()
        mock_logfile.a_exists = AsyncMock(return_value=True)
        mock_handler = Mock()
        mock_handler.read = AsyncMock(return_value=b" completed\nline2\n")
        mock_handler.__aenter__ = AsyncMock(return_value=mock_handler)
        mock_logfile.a_open = Mock(return_value=mock_handler)

        populator = LogsPopulator()
        populator.logfile = mock_logfile
        populator.residue = b"partial"

        result = await populator.populate()
        assert result == ["partial completed", "line2"]
        populator.increment_counter()
        assert populator.counter == 1
        assert populator.residue == b""

    async def test_populate_multiple_calls_reuses_handler(self):
        """Test that multiple populate calls reuse the same file handler."""
        mock_logfile = Mock()
        mock_logfile.a_exists = AsyncMock(return_value=True)
        mock_handler = Mock()
        mock_handler.read = AsyncMock(return_value=b"new content\n")
        mock_handler.__aenter__ = AsyncMock(return_value=mock_handler)
        mock_logfile.a_open = Mock(return_value=mock_handler)

        populator = LogsPopulator()
        populator.logfile = mock_logfile

        # First call
        result1 = await populator.populate()  # noqa: F841
        first_handler = populator.handler

        # Second call should reuse handler
        result2 = await populator.populate()  # noqa: F841
        second_handler = populator.handler

        assert first_handler is second_handler
        assert mock_logfile.a_open.call_count == 1

    async def test_populate_only_residue_no_newlines(self):
        """Test populate with content that has no newlines."""
        content = b"no newlines here"
        mock_logfile = Mock()
        mock_logfile.a_exists = AsyncMock(return_value=True)
        mock_handler = Mock()
        mock_handler.read = AsyncMock(return_value=content)
        mock_handler.__aenter__ = AsyncMock(return_value=mock_handler)
        mock_logfile.a_open = Mock(return_value=mock_handler)

        populator = LogsPopulator()
        populator.logfile = mock_logfile

        result = await populator.populate()
        assert result == []
        assert populator.residue == b"no newlines here"

    async def test_destroy_closes_handler(self):
        """Test that destructor closes the file handler."""
        mock_handler = Mock()
        mock_handler.close = AsyncMock()

        populator = LogsPopulator()
        populator.handler = mock_handler

        await populator.destroy()
        assert populator.handler is None
        mock_handler.close.assert_called_once()

    def test_slots_attribute(self):
        """Test that the class uses __slots__ correctly."""
        populator = LogsPopulator()

        # Should have these attributes
        assert hasattr(populator, 'logfile')
        assert hasattr(populator, 'handler')
        assert hasattr(populator, 'residue')
        assert hasattr(populator, 'counter')

        # Should not be able to add arbitrary attributes
        with pytest.raises(AttributeError):
            populator.some_other_attribute = "value"
