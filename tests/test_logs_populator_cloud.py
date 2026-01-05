import os
import sys
import pytest
from panpath import PanPath
from pipen_poplog import LogsPopulator

# skip if GOOGLE_APPLICATION_CREDENTIALS is not set
pytestmark = pytest.mark.skipif(
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is None,
    reason="GOOGLE_APPLICATION_CREDENTIALS is not set",
)

BUCKET = "gs://handy-buffer-287000.appspot.com"


@pytest.fixture
async def testdir(request):
    """Fixture to auto-clean test artifacts after test."""
    requestid = hash((request.node.name, sys.executable, sys.version_info)) & 0xFFFFFFFF
    outdir = PanPath(
        f"{BUCKET}/pipen-poplog-tests/test_logs_populator_cloud.{requestid}"
    )
    await outdir.a_mkdir(exist_ok=True, parents=True)
    yield outdir
    # Cleanup
    await outdir.a_rmtree(ignore_errors=True)


async def test_populate_complete_lines(testdir):
    """Test populate method with complete lines ending with newline."""
    content = "line1\nline2\nline3\n"

    populator = LogsPopulator()
    populator.logfile = testdir / "logfile.log"
    await populator.logfile.a_write_text(content)

    result = await populator.populate()
    assert result == ["line1", "line2", "line3"]
    populator.increment_counter()
    assert populator.counter == 1
    assert populator.residue == ""


async def test_populate_incomplete_last_line(testdir):
    """Test populate method with incomplete last line (no trailing newline)."""
    content = "line1\nline2\nincomplete"

    populator = LogsPopulator()
    populator.logfile = testdir / "logfile.log"
    await populator.logfile.a_write_text(content)

    result = await populator.populate()
    assert result == ["line1", "line2"]
    populator.increment_counter()
    assert populator.counter == 1
    assert populator.residue == "incomplete"


async def test_populate_with_residue_from_previous_read(testdir):
    """Test populate method using residue from previous read."""
    populator = LogsPopulator()
    populator.logfile = testdir / "logfile.log"
    populator.residue = "partial"
    await populator.logfile.a_write_text(" completed\nline2\n")

    result = await populator.populate()
    assert result == ["partial completed", "line2"]
    populator.increment_counter()
    assert populator.counter == 1
    assert populator.residue == ""


async def test_populate_multiple_calls_reuses_handler(testdir):
    """Test that multiple populate calls reuse the same file handler."""
    populator = LogsPopulator()
    populator.logfile = testdir / "logfile.log"
    await populator.logfile.a_write_text("new content\n")

    # First call
    result1 = await populator.populate()  # noqa: F841
    first_handler = populator.handler

    # Second call should reuse handler
    result2 = await populator.populate()  # noqa: F841
    second_handler = populator.handler

    assert first_handler is second_handler


async def test_populate_only_residue_no_newlines(testdir):
    """Test populate with content that has no newlines."""
    content = "no newlines here"

    populator = LogsPopulator()
    populator.logfile = testdir / "logfile.log"
    await populator.logfile.a_write_text(content)

    result = await populator.populate()
    assert result == []
    assert populator.residue == "no newlines here"
