# Makefile for MiniSEED Pipeline Converter

.PHONY: help install install-dev test lint format clean build upload docs security

# Default target
help:
	@echo "Available targets:"
	@echo "  install      Install package dependencies"
	@echo "  install-dev  Install development dependencies"
	@echo "  test         Run test suite"
	@echo "  lint         Run code linting"
	@echo "  format       Format code with black and isort"
	@echo "  clean        Clean build artifacts"
	@echo "  build        Build distribution packages"
	@echo "  upload       Upload to PyPI (use upload-test for TestPyPI)"
	@echo "  docs         Generate documentation"
	@echo "  security     Run security checks"
	@echo "  all          Run format, lint, test, and security checks"

# Installation targets
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

# Testing targets
test:
	pytest tests/ -v --cov=mseed_pipeline_converter --cov-report=html --cov-report=term

test-quick:
	pytest tests/ -x -v

# Code quality targets
lint:
	flake8 mseed_pipeline_converter.py
	mypy mseed_pipeline_converter.py --ignore-missing-imports

format:
	black mseed_pipeline_converter.py
	isort mseed_pipeline_converter.py

format-check:
	black --check mseed_pipeline_converter.py
	isort --check-only mseed_pipeline_converter.py

# Security targets
security:
	bandit -r mseed_pipeline_converter.py
	safety check -r requirements.txt

# Documentation targets
docs:
	@echo "Generating documentation..."
	python -c "import mseed_pipeline_converter; help(mseed_pipeline_converter)"

# Build targets
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

build: clean
	python -m build

# Upload targets
upload-test: build
	python -m twine upload --repository testpypi dist/*

upload: build
	python -m twine upload dist/*

# Development workflow targets
all: format lint test security
	@echo "All checks passed!"

dev-setup: install-dev
	pre-commit install

# Continuous integration targets
ci: format-check lint test security
	@echo "CI checks completed!"

# Release targets
release-check:
	@echo "Checking release readiness..."
	@python -c "import mseed_pipeline_converter; print(f'Version: {mseed_pipeline_converter.__version__}')"
	@git status --porcelain | grep -q . && echo "Working directory not clean!" && exit 1 || echo "Working directory clean"
	@echo "Ready for release!"

# Example targets
run-example:
	python mseed_pipeline_converter.py --help

run-interactive:
	python mseed_pipeline_converter.py

# Performance targets
profile:
	python -m cProfile -s cumulative mseed_pipeline_converter.py --help

# Container targets (if Docker support added later)
docker-build:
	docker build -t mseed-pipeline-converter .

docker-run:
	docker run --rm -it mseed-pipeline-converter --help