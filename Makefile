POETRY ?= poetry
IMAGE ?= tno-portal

.PHONY: build coverage docker-build install run test

install:
	$(POETRY) install

test:
	$(POETRY) run pytest

coverage:
	$(POETRY) run coverage run -m pytest
	$(POETRY) run coverage report -m

build:
	docker build -t $(IMAGE) .

docker-build: build

run:
	$(POETRY) run gunicorn --bind 0.0.0.0:8000 wsgi:app
