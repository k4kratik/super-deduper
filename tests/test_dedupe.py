"""Tests for the dedupe pipeline."""

import asyncio
import tempfile
from pathlib import Path

import pytest
import redis

from dedupe.main import DedupePipeline


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def redis_client():
    """Create a Redis client for testing."""
    redis_client = redis.from_url("redis://localhost:6379/15")  # Use DB 15 for testing
    yield redis_client
    redis_client.flushdb()
    redis_client.close()


@pytest.fixture
def pipeline(temp_dir, redis_client):
    """Create a dedupe pipeline for testing."""
    pipeline = DedupePipeline(str(temp_dir / "db"), "redis://localhost:6379/15")
    pipeline.initialize()
    yield pipeline
    pipeline.close()


def test_calculate_file_hash(pipeline, temp_dir):
    """Test file hash calculation."""
    # Create a test file
    test_file = temp_dir / "test.txt"
    test_file.write_text("Hello, World!")

    hash1 = pipeline.calculate_file_hash(test_file)
    hash2 = pipeline.calculate_file_hash(test_file)

    # Same file should produce same hash
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 produces 64 character hex string


def test_process_unique_file(pipeline, temp_dir):
    """Test processing a unique file."""
    # Create a test file
    test_file = temp_dir / "unique.txt"
    test_file.write_text("This is a unique file")

    result = pipeline.process_file(test_file)

    assert result["status"] == "unique"
    assert "hash" in result


def test_process_duplicate_file(pipeline, temp_dir):
    """Test processing duplicate files."""
    # Create two identical files
    file1 = temp_dir / "file1.txt"
    file2 = temp_dir / "file2.txt"
    content = "This is duplicate content"
    file1.write_text(content)
    file2.write_text(content)

    # Process first file
    result1 = pipeline.process_file(file1)
    assert result1["status"] == "unique"

    # Process second file (should be duplicate)
    result2 = pipeline.process_file(file2)
    assert result2["status"] == "duplicate"
    assert result1["hash"] == result2["hash"]


def test_scan_directory(pipeline, temp_dir):
    """Test directory scanning."""
    # Create test files
    (temp_dir / "file1.txt").write_text("content1")
    (temp_dir / "file2.txt").write_text("content2")
    (temp_dir / "subdir").mkdir()
    (temp_dir / "subdir" / "file3.txt").write_text("content3")

    files = pipeline.scan_directory(temp_dir)

    # Filter out database files
    files = [f for f in files if not f.name.endswith(".db")]

    assert len(files) == 3
    assert all(f.is_file() for f in files)


def test_run_deduplication(pipeline, temp_dir):
    """Test full deduplication process."""
    # Create test files with some duplicates
    (temp_dir / "file1.txt").write_text("content1")
    (temp_dir / "file2.txt").write_text("content2")
    (temp_dir / "file3.txt").write_text("content1")  # Duplicate of file1

    stats = pipeline.run_deduplication(temp_dir)

    # The database file gets created during processing, so we expect 3 unique files
    # (file1, file2, and the database file) and 1 duplicate (file3)
    assert stats["unique"] == 3  # file1, file2, and database file
    assert stats["duplicate"] == 1  # file3
    assert stats["errors"] == 0


def test_nonexistent_file(pipeline, temp_dir):
    """Test processing a non-existent file."""
    nonexistent_file = temp_dir / "nonexistent.txt"

    result = pipeline.process_file(nonexistent_file)

    assert result["status"] == "error"
    assert "does not exist" in result["message"]
