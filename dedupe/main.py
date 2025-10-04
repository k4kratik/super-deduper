"""Main CLI for the dedupe pipeline."""

import asyncio
import hashlib
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

import click
import redis

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DedupePipeline:
    """Simple file deduplication pipeline."""

    def __init__(self, db_path: str, redis_url: str = "redis://localhost:6379/0"):
        self.db_path = Path(db_path)
        self.redis_url = redis_url
        self.db: sqlite3.Connection = None
        self.redis: redis.Redis = None

    def initialize(self):
        """Initialize database and Redis connections."""
        # Initialize SQLite
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.db_path / "dedupe.db"))
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS file_hashes (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                file_mtime REAL NOT NULL,
                file_size INTEGER NOT NULL
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS hash_files (
                file_hash TEXT,
                file_path TEXT,
                file_mtime REAL NOT NULL,
                file_size INTEGER NOT NULL,
                PRIMARY KEY (file_hash, file_path)
            )
            """
        )
        self.db.commit()

        # Initialize Redis
        self.redis = redis.from_url(self.redis_url)
        self.redis.ping()

        logger.info("Initialized dedupe pipeline")

    def close(self):
        """Close connections."""
        if self.redis:
            self.redis.close()
        if self.db:
            self.db.close()

    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def process_file(self, file_path: Path) -> Dict[str, any]:
        """Process a single file for deduplication."""
        try:
            if not file_path.exists():
                return {"status": "error", "message": "File does not exist"}

            # Get file metadata
            stat = file_path.stat()
            file_mtime = stat.st_mtime
            file_size = stat.st_size
            file_hash = self.calculate_file_hash(file_path)

            # Check if hash exists in SQLite
            cursor = self.db.execute(
                "SELECT file_path FROM hash_files WHERE file_hash = ?", (file_hash,)
            )
            existing_files = [row[0] for row in cursor.fetchall()]

            if existing_files:
                # Duplicate found - add to hash_files table for reporting
                self.db.execute(
                    "INSERT OR REPLACE INTO hash_files (file_hash, file_path, file_mtime, file_size) VALUES (?, ?, ?, ?)",
                    (file_hash, str(file_path), file_mtime, file_size),
                )
                self.db.commit()
                self.redis.sadd("duplicates", str(file_path))
                return {
                    "status": "duplicate",
                    "hash": file_hash,
                    "existing_files": existing_files,
                }
            else:
                # First occurrence
                self.db.execute(
                    "INSERT OR REPLACE INTO file_hashes (file_path, file_hash, file_mtime, file_size) VALUES (?, ?, ?, ?)",
                    (str(file_path), file_hash, file_mtime, file_size),
                )
                self.db.execute(
                    "INSERT OR REPLACE INTO hash_files (file_hash, file_path, file_mtime, file_size) VALUES (?, ?, ?, ?)",
                    (file_hash, str(file_path), file_mtime, file_size),
                )
                self.db.commit()
                self.redis.sadd("unique_files", str(file_path))
                return {"status": "unique", "hash": file_hash}

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return {"status": "error", "message": str(e)}

    def scan_directory(self, directory: Path) -> List[Path]:
        """Scan directory for files to process."""
        files = []
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                files.append(file_path)
        return files

    def run_deduplication(self, scan_path: Path, max_workers: int = None) -> Dict[str, int]:
        """Run deduplication on a directory with parallel processing."""
        logger.info(f"Starting deduplication of {scan_path}")

        files = self.scan_directory(scan_path)
        total_files = len(files)
        logger.info(f"Found {total_files} files to process")

        # Auto-detect optimal worker count if not specified
        if max_workers is None:
            import os
            max_workers = min(32, (os.cpu_count() or 1) + 4)  # I/O bound, so more workers than CPU cores

        logger.info(f"Using {max_workers} parallel workers")

        stats = {"unique": 0, "duplicate": 0, "errors": 0}
        processed_count = 0

        # Use ThreadPoolExecutor for I/O bound operations
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all file processing tasks
            future_to_file = {
                executor.submit(self._process_file_worker, file_path): file_path 
                for file_path in files
            }

            # Process completed tasks as they finish
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                processed_count += 1
                
                # Progress indicator
                progress = f"[{processed_count}/{total_files}]"
                remaining = total_files - processed_count
                print(f"\r{progress} Processing... ({remaining} remaining)", end="", flush=True)
                
                try:
                    result = future.result()
                    status = result["status"]
                    if status in stats:
                        stats[status] += 1
                    else:
                        stats[status] = 1

                    if result["status"] == "duplicate":
                        logger.debug(f"Duplicate: {file_path} (hash: {result['hash'][:8]}...)")
                    elif result["status"] == "unique":
                        logger.debug(f"Unique: {file_path}")
                    else:
                        logger.error(f"Error: {file_path} - {result['message']}")
                        
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    stats["errors"] += 1

        # Clear progress line
        print("\r" + " " * 50 + "\r", end="", flush=True)
        return stats

    def _process_file_worker(self, file_path: Path) -> Dict[str, any]:
        """Worker method for parallel file processing."""
        try:
            if not file_path.exists():
                return {"status": "error", "message": "File does not exist"}

            # Get file metadata
            stat = file_path.stat()
            file_mtime = stat.st_mtime
            file_size = stat.st_size
            file_hash = self.calculate_file_hash(file_path)

            # Create a new database connection for this thread
            thread_db = sqlite3.connect(str(self.db_path / "dedupe.db"))
            thread_redis = redis.from_url(self.redis_url)

            try:
                # Check if hash exists in SQLite
                cursor = thread_db.execute(
                    "SELECT file_path FROM hash_files WHERE file_hash = ?", (file_hash,)
                )
                existing_files = [row[0] for row in cursor.fetchall()]

                if existing_files:
                    # Duplicate found - add to hash_files table for reporting
                    thread_db.execute(
                        "INSERT OR REPLACE INTO hash_files (file_hash, file_path, file_mtime, file_size) VALUES (?, ?, ?, ?)",
                        (file_hash, str(file_path), file_mtime, file_size),
                    )
                    thread_db.commit()
                    thread_redis.sadd("duplicates", str(file_path))
                    return {
                        "status": "duplicate",
                        "hash": file_hash,
                        "existing_files": existing_files,
                    }
                else:
                    # First occurrence
                    thread_db.execute(
                        "INSERT OR REPLACE INTO file_hashes (file_path, file_hash, file_mtime, file_size) VALUES (?, ?, ?, ?)",
                        (str(file_path), file_hash, file_mtime, file_size),
                    )
                    thread_db.execute(
                        "INSERT OR REPLACE INTO hash_files (file_hash, file_path, file_mtime, file_size) VALUES (?, ?, ?, ?)",
                        (file_hash, str(file_path), file_mtime, file_size),
                    )
                    thread_db.commit()
                    thread_redis.sadd("unique_files", str(file_path))
                    return {"status": "unique", "hash": file_hash}
            finally:
                thread_db.close()
                thread_redis.close()

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return {"status": "error", "message": str(e)}

    def _get_db_lock(self):
        """Get a thread lock for database operations."""
        if not hasattr(self, '_db_lock'):
            import threading
            self._db_lock = threading.Lock()
        return self._db_lock

    def calculate_duplicate_size(self) -> int:
        """Calculate total size of duplicate files (excluding originals)."""
        if not self.db:
            return 0
        
        # Get all duplicate groups
        cursor = self.db.execute("""
            SELECT file_hash, GROUP_CONCAT(file_path || '|' || file_mtime || '|' || file_size, '||') as files
            FROM hash_files 
            GROUP BY file_hash 
            HAVING COUNT(*) > 1
        """)
        
        duplicate_groups = cursor.fetchall()
        total_duplicate_size = 0
        
        for file_hash, files_str in duplicate_groups:
            file_data = []
            for file_info in files_str.split('||'):
                if file_info:
                    parts = file_info.split('|')
                    if len(parts) >= 3:
                        file_path, mtime, size = parts[0], float(parts[1]), int(parts[2])
                        file_data.append((file_path, mtime, size))
            
            if len(file_data) > 1:
                # Sort by modification time (oldest first)
                file_data.sort(key=lambda x: x[1])
                # Add size of all files except the first (original)
                for i, (file_path, mtime, size) in enumerate(file_data):
                    if i > 0:  # Skip the original (first file)
                        total_duplicate_size += size
        
        return total_duplicate_size

    def generate_markdown_report(self, output_path: Path = None) -> str:
        """Generate a markdown report of duplicate files."""
        if not self.db:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        # Get all duplicate groups from database, ordered by modification time (oldest first)
        cursor = self.db.execute("""
            SELECT file_hash, 
                   GROUP_CONCAT(file_path || '|' || file_mtime || '|' || file_size, '||') as files
            FROM hash_files 
            GROUP BY file_hash 
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, file_hash
        """)
        
        duplicate_groups = cursor.fetchall()
        
        # Get statistics
        total_files = self.db.execute("SELECT COUNT(*) FROM hash_files").fetchone()[0]
        unique_hashes = self.db.execute("SELECT COUNT(DISTINCT file_hash) FROM hash_files").fetchone()[0]
        duplicate_files = 0
        for file_hash, files_str in duplicate_groups:
            file_data = []
            for file_info in files_str.split('||'):
                if file_info:
                    parts = file_info.split('|')
                    if len(parts) >= 3:
                        file_data.append(parts[0])
            duplicate_files += len(file_data) - 1  # All but the first are duplicates
        space_saved = 0
        
        # Calculate space that could be saved
        for file_hash, files_str in duplicate_groups:
            file_data = []
            for file_info in files_str.split('||'):
                if file_info:
                    parts = file_info.split('|')
                    if len(parts) >= 3:
                        file_path, mtime, size = parts[0], float(parts[1]), int(parts[2])
                        file_data.append((file_path, mtime, size))
            
            if len(file_data) > 1:
                # Use the size from the first file (they should all be the same size)
                file_size = file_data[0][2]
                space_saved += file_size * (len(file_data) - 1)  # Save (n-1) copies
        
        # Generate markdown content
        report_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate percentages safely
        unique_files = total_files - duplicate_files
        unique_pct = (unique_files / total_files * 100) if total_files > 0 else 0
        duplicate_pct = (duplicate_files / total_files * 100) if total_files > 0 else 0
        
        markdown = f"""# Duplicate Files Report

**Generated:** {report_date}

## Summary

| Metric | Count | Percentage |
|--------|-------|------------|
| Total Files | {total_files:,} | 100.0% |
| Unique Files | {unique_files:,} | {unique_pct:.1f}% |
| Duplicate Files | {duplicate_files:,} | {duplicate_pct:.1f}% |
| Unique Hashes | {unique_hashes:,} | - |
| Duplicate Groups | {len(duplicate_groups):,} | - |

## Space Analysis

**Potential Space Savings:** {self._format_bytes(space_saved)}

## Duplicate Groups

"""
        
        if not duplicate_groups:
            markdown += "*No duplicate files found.*\n"
        else:
            for i, (file_hash, files_str) in enumerate(duplicate_groups, 1):
                # Parse file data: file_path|mtime|size||file_path|mtime|size||...
                file_data = []
                for file_info in files_str.split('||'):
                    if file_info:
                        parts = file_info.split('|')
                        if len(parts) >= 3:
                            file_path, mtime, size = parts[0], float(parts[1]), int(parts[2])
                            file_data.append((file_path, mtime, size))
                
                # Sort by modification time (oldest first - oldest is original)
                file_data.sort(key=lambda x: x[1])
                group_size = len(file_data)
                
                # Get file size for the group (use first file's size)
                file_size = self._format_bytes(file_data[0][2]) if file_data else "Unknown"
                
                markdown += f"### Group {i} ({group_size} files, {file_size} each)\n\n"
                markdown += f"**Hash:** `{file_hash}`\n\n"
                markdown += "**Files:**\n"
                
                for j, (file_path, mtime, size) in enumerate(file_data, 1):
                    # Convert mtime to readable date
                    mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    
                    if j == 1:
                        status = "👑 **Original** (oldest)"
                    else:
                        status = "🔄 **Duplicate**"
                    
                    markdown += f"{j}. {status} `{file_path}` ({mtime_str})\n"
                
                markdown += "\n---\n\n"
        
        # Save to file if path provided
        if output_path:
            output_path.write_text(markdown, encoding='utf-8')
            logger.info(f"Markdown report saved to: {output_path}")
        
        return markdown

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes into human readable format."""
        if bytes_value == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"


@click.group()
def cli():
    """Simple file deduplication pipeline."""
    pass


@cli.command()
@click.option("--scan-path", "-s", required=True, help="Directory to scan for files")
@click.option("--db-path", "-d", default="./data", help="Database storage path")
@click.option("--redis-url", "-r", default="redis://localhost:6379/0", help="Redis URL")
@click.option("--no-report", is_flag=True, help="Skip generating markdown report")
@click.option("--report-output", "-o", help="Report output file (default: duplicate_report_folder_timestamp.md)")
@click.option("--workers", "-w", type=int, help="Number of parallel workers (auto-detected if not specified)")
def deduplicate(scan_path: str, db_path: str, redis_url: str, no_report: bool, report_output: str, workers: int):
    """Run deduplication on a directory."""
    pipeline = DedupePipeline(db_path, redis_url)
    try:
        pipeline.initialize()
        stats = pipeline.run_deduplication(Path(scan_path), max_workers=workers)

        total_files = sum(stats.values())
        unique_pct = (stats['unique'] / total_files * 100) if total_files > 0 else 0
        duplicate_pct = (stats['duplicate'] / total_files * 100) if total_files > 0 else 0
        error_pct = (stats['errors'] / total_files * 100) if total_files > 0 else 0
        
        # Calculate total size of duplicate files
        duplicate_size = pipeline.calculate_duplicate_size()
        
        print("\n=== Deduplication Results ===")
        print(f"Unique files: {stats['unique']} ({unique_pct:.1f}%)")
        print(f"Duplicate files: {stats['duplicate']} ({duplicate_pct:.1f}%)")
        print(f"Errors: {stats['errors']} ({error_pct:.1f}%)")
        print(f"Total files: {total_files}")
        print(f"Duplicate files size: {pipeline._format_bytes(duplicate_size)}")

        # Generate markdown report by default
        if not no_report:
            if report_output:
                report_path = Path(report_output)
            else:
                # Generate dynamic report name: folder_name_YYYY-MM-DD_HH-MM-SS.md
                folder_name = Path(scan_path).name
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                report_path = Path(f"duplicate_report_{folder_name}_{timestamp}.md")
            
            pipeline.generate_markdown_report(report_path)
            print(f"\n📊 Markdown report generated: {report_path.absolute()}")

    finally:
        pipeline.close()


@cli.command()
@click.option("--db-path", "-d", default="./data", help="Database storage path")
def stats(db_path: str):
    """Show deduplication statistics."""
    pipeline = DedupePipeline(db_path)
    try:
        pipeline.initialize()

        # Count unique files
        unique_count = pipeline.redis.scard("unique_files")
        duplicate_count = pipeline.redis.scard("duplicates")

        print(f"Unique files: {unique_count}")
        print(f"Duplicate files: {duplicate_count}")

    finally:
        pipeline.close()


@cli.command()
@click.option("--db-path", "-d", default="./data", help="Database storage path")
def clean(db_path: str):
    """Clean up database and Redis data."""
    pipeline = DedupePipeline(db_path)
    try:
        pipeline.initialize()

        # Clear Redis sets
        pipeline.redis.delete("unique_files")
        pipeline.redis.delete("duplicates")

        print("Cleaned up Redis data")

    finally:
        pipeline.close()


@cli.command()
@click.option("--db-path", "-d", default="./data", help="Database storage path")
@click.option("--output", "-o", help="Output file path (default: duplicate_report.md)")
@click.option("--print", "print_report", is_flag=True, help="Print report to console")
def report(db_path: str, output: str, print_report: bool):
    """Generate a markdown report of duplicate files."""
    pipeline = DedupePipeline(db_path)
    try:
        pipeline.initialize()
        
        # Determine output path
        if output:
            output_path = Path(output)
        else:
            output_path = Path("duplicate_report.md")
        
        # Generate report
        markdown_content = pipeline.generate_markdown_report(output_path)
        
        if print_report:
            print("\n" + "="*50)
            print(markdown_content)
            print("="*50)
        else:
            print(f"Report generated: {output_path.absolute()}")

    finally:
        pipeline.close()


if __name__ == "__main__":
    cli()
