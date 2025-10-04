# Super Deduper 🚀

*Because your storage is a mess and we're here to fix it.*

Super Deduper is a lightning-fast file deduplication pipeline that finds duplicate files, shows you exactly what's wasting space, and generates beautiful reports so you can actually understand what's going on.

## Why Super Deduper?

- **⚡ Blazing Fast**: Parallel processing - 2.5x faster than sequential
- **📊 Smart Reports**: Knows which file is the "original" (oldest wins)
- **💾 Size Tracking**: Shows total size of duplicate files at a glance
- **🎯 Accurate**: SHA-256 hashing means zero false positives
- **📱 Simple**: One command, done. No nonsense.

## Quick Start

```bash
# Install dependencies
uv sync

# Start Redis (if you don't have it)
make up

# Find duplicates and get a report
uv run dedupe deduplicate --scan-path /path/to/your/mess

# Done. Check duplicate_report.md for the goods.
```

## What You Get

### 📈 Real-time Progress
```
[1,234/5,000] Processing... (3,766 remaining)
=== Deduplication Results ===
Unique files: 3,391 (67.8%)
Duplicate files: 1,609 (32.2%)
Total files: 5,000
Duplicate files size: 12.6 MB

📊 Markdown report generated: /path/to/duplicate_report_my_folder_2025-10-04_19-35-17.md
```

### 📋 Smart Reports
Your report shows:
- **Summary stats** with percentages
- **Space savings** (how much you can free up)
- **Duplicate groups** with timestamps
- **Original vs duplicates** (oldest file wins the crown 👑)
- **Dynamic naming**: `duplicate_report_folder_name_2025-10-04_19-35-17.md`

Example:
```markdown
### Group 1 (3 files, 2.1 MB each)

**Hash:** `d2a84f4b8b650937ec8f73cd8be2c74add5a911ba64df27458ed8229da804a26`

**Files:**
1. 👑 **Original** (oldest) `photos/vacation.jpg` (2023-10-01 12:00:00)
2. 🔄 **Duplicate** `backup/vacation_copy.jpg` (2023-10-02 15:30:00)
3. 🔄 **Duplicate** `temp/vacation_temp.jpg` (2023-10-03 09:15:00)
```

## Commands That Matter

```bash
# The main event (auto-detects optimal workers)
uv run dedupe deduplicate --scan-path /your/files

# Control parallel workers (more = faster, but uses more resources)
uv run dedupe deduplicate --scan-path /your/files --workers 8

# Skip the report (why would you?)
uv run dedupe deduplicate --scan-path /your/files --no-report

# Custom report name (overrides auto-naming)
uv run dedupe deduplicate --scan-path /your/files --report-output my_cleanup.md

# Quick stats
uv run dedupe stats

# Clean slate
uv run dedupe clean
```

## Makefile Shortcuts

```bash
make up          # Start Redis
make down        # Stop Redis
make dedupe      # Dedupe current directory
make report      # Generate report manually
make clean-all   # Nuclear option - clean everything
```

## Test It Out

Want to see it in action? Generate some test data:

```bash
# Create 1000 dummy images with 30% duplicates
make create-images

# Dedupe them
uv run dedupe deduplicate --scan-path dummy_images

# Marvel at your report
cat duplicate_report.md
```

## Requirements

- Python 3.12+
- Redis (we'll start it for you)
- Some files to dedupe (obviously)

## How It Works

1. **Scans** your directory for files
2. **Processes in parallel** using ThreadPoolExecutor (I/O bound operations)
3. **Hashes** each file with SHA-256
4. **Compares** hashes to find duplicates
5. **Stores** everything in SQLite (fast, reliable, thread-safe)
6. **Reports** what it found (with timestamps for smart original detection)

**Performance**: Auto-detects optimal worker count (CPU cores + 4), but you can override it. More workers = faster processing for I/O bound operations.

**Speed Test Results** (7,585 files):
- **1 worker**: 19.3 seconds (sequential)
- **15 workers**: 7.5 seconds (parallel)
- **Speedup**: 2.5x faster! 🚀

The "original" file is always the oldest one. Because logic.

## Data Storage

- **SQLite**: Stores file paths, hashes, timestamps, and sizes
- **Redis**: Tracks statistics during processing

## License

MIT. Use it, abuse it, just don't blame us if you delete the wrong files.

---

*Super Deduper: Making your storage great again.* 🎯