POETRY ?= poetry
IMAGE ?= tno-portal
PYTHON ?= python3
TRANSLATE_SCRIPT ?= scripts/generate_translations.py

.PHONY: build coverage docker-build install run test test-local translate translate-force

install:
	$(POETRY) install

test:
	$(POETRY) run pytest

test-local: translate
	$(POETRY) run pytest

translate:
	$(PYTHON) $(TRANSLATE_SCRIPT)

translate-force:
	$(PYTHON) $(TRANSLATE_SCRIPT) --force

coverage:
	$(POETRY) run coverage run -m pytest
	$(POETRY) run coverage report -m

build:
	docker build -t $(IMAGE) .

docker-build: build

run:
	$(POETRY) run gunicorn --bind 0.0.0.0:8000 wsgi:app
