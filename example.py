#!/usr/bin/env python3
"""Example usage of the dedupe pipeline."""

import asyncio
import tempfile
from pathlib import Path

from dedupe.main import DedupePipeline


def main():
    """Example of using the dedupe pipeline."""
    # Create a temporary directory with some test files
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)

        # Create some test files
        (test_dir / "file1.txt").write_text("Hello, World!")
        (test_dir / "file2.txt").write_text("This is different content")
        (test_dir / "file3.txt").write_text("Hello, World!")  # Duplicate of file1
        (test_dir / "file4.txt").write_text("Another unique file")

        # Create subdirectory with more files
        subdir = test_dir / "subdir"
        subdir.mkdir()
        (subdir / "file5.txt").write_text("Hello, World!")  # Another duplicate
        (subdir / "file6.txt").write_text("Subdirectory content")

        print(f"Created test files in: {test_dir}")
        print("Files created:")
        for file_path in test_dir.rglob("*"):
            if file_path.is_file():
                print(f"  {file_path.relative_to(test_dir)}")

        # Initialize the dedupe pipeline
        pipeline = DedupePipeline("./example-data")

        try:
            pipeline.initialize()

            # Run deduplication
            print("\nRunning deduplication...")
            stats = pipeline.run_deduplication(test_dir)

            print("\n=== Results ===")
            print(f"Unique files: {stats['unique']}")
            print(f"Duplicate files: {stats['duplicate']}")
            print(f"Errors: {stats['errors']}")
            print(f"Total files: {sum(stats.values())}")

            # Show statistics
            print("\n=== Statistics ===")
            unique_count = pipeline.redis.scard("unique_files")
            duplicate_count = pipeline.redis.scard("duplicates")
            print(f"Unique files in Redis: {unique_count}")
            print(f"Duplicate files in Redis: {duplicate_count}")

        finally:
            pipeline.close()


if __name__ == "__main__":
    main()
