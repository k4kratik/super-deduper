.PHONY: help install dev test format lint check up down logs status dedupe report clean-all create-images

# Default target
help: ## Show this help message
	@echo "Super Deduper - File Deduplication Pipeline"
	@echo "=========================================="
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Setup
install: ## Install dependencies
	uv sync

dev: ## Install development dependencies
	uv sync --dev

# Development
test: ## Run tests
	uv run pytest

format: ## Format code
	uv run black .
	uv run isort .

lint: ## Run linting
	uv run mypy .

check: format lint test ## Run all checks

# Redis operations
up: ## Start Redis with Docker Compose
	docker-compose up -d

down: ## Stop and remove Redis container
	docker-compose down

logs: ## Show Redis logs
	docker-compose logs -f redis

status: ## Show Redis status
	docker-compose ps

# Main operations
dedupe: ## Run deduplication on current directory (generates report by default)
	uv run dedupe deduplicate --scan-path .

report: ## Generate markdown report of duplicate files
	uv run dedupe report

clean-all: ## Clean up all data (Redis + SQLite database)
	uv run dedupe clean
	rm -rf data/ example-data/

# Test data generation
create-images: ## Create dummy images for testing (1000 images, 30% duplicates)
	uv run python create_dummy_images.py --count 1000 --duplicates 0.3