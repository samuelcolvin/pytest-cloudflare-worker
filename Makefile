.DEFAULT_GOAL := all
isort = isort pytest_cloudflare_worker tests
black = black -S -l 120 --target-version py38 pytest_cloudflare_worker tests

.PHONY: install
install:
	pip install -U setuptools pip
	pip install -r tests/requirements.txt
	pip install -r tests/requirements-linting.txt
	pip install -e .

.PHONY: format
format:
	$(isort)
	$(black)

.PHONY: lint
lint:
	flake8 pytest_cloudflare_worker/ tests/
	$(isort) --check-only --df
	$(black) --check --diff

.PHONY: test
test:
	pytest --cov=pytest_cloudflare_worker

.PHONY: testcov
testcov:
	pytest --cov=pytest_cloudflare_worker
	@echo "building coverage html"
	@coverage html

.PHONY: all
all: lint testcov

.PHONY: clean
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -rf .cache
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf *.egg-info
	rm -f .coverage
	rm -f .coverage.*
	rm -rf build
	rm -rf dist
	python setup.py clean
