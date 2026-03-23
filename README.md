# TNO Portal

Flask web application for TNO, TON, and TCF alliance workflows for Puzzles and Survival.

## Requirements

- Python 3.12+
- Poetry 2.x
- Docker
- Access to MongoDB

## Configuration

The app uses these key environment variables:

- `SECRET_KEY`
- `APP_DATA_DIR` default: `./data` locally, `/app/data` in Docker
- `MONGO_URI` default: `mongodb://192.168.215.2:27017/`
- `MONGO_DB_NAME` default: `TNO-MongoDB`
- `MONGO_COLLECTION_NAME` default: `users`
- `SESSION_COOKIE_SECURE` default: `false`

Persistent app logs and config live in `APP_DATA_DIR`. MongoDB is used for account persistence.

## Local Development

Install dependencies:

```bash
make install
```

Run the app with Gunicorn:

```bash
make run
```

Open `http://127.0.0.1:8000`.

For local testing, `make run` defaults to `mongodb://192.168.215.2:27017/`. Override `MONGO_URI` to point at a different host or port when needed.

## Testing

Run tests:

```bash
make test
```

Run coverage:

```bash
make coverage
```

## Docker

Build the image:

```bash
make build
```

Run with Docker Compose:

```bash
docker compose up --build
```

The container exposes port `8000` and mounts `./data` to `/app/data`.
