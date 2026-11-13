
# AGORA Local Development

## Recommended development setup

Use Docker Compose to run PostgreSQL, Redis, FastAPI and the React frontend.

This is the recommended common setup for Linux and macOS.

## First time configuration

1. Install Docker Desktop on macOS or Docker Engine and the Compose plugin on Linux.
2. Copy the root `.env.example` to `.env`.
3. Set a unique local PostgreSQL password in `.env`.
4. Copy `backend/.env.example` to `backend/.env` only if the real file does not already exist.
5. Add valid provider API keys to `backend/.env`.
6. Never commit real environment files.

## Validate and start

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Do not run the normal, unredacted `docker compose config` command when provider keys are present. The resolved output may expose credentials.

## Local URLs

Frontend:

http://localhost:5173

Backend health:

http://127.0.0.1:8000/health

Backend health through frontend proxy:

http://localhost:5173/api/health

PostgreSQL:

127.0.0.1:5432

Redis:

127.0.0.1:6379

## Useful commands

```bash
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 postgres
docker compose logs --tail=100 redis
docker compose restart backend
docker compose restart frontend
docker compose down
```

`docker compose down` preserves named volumes.

Do not use `docker compose down -v` unless you intentionally want to delete local PostgreSQL and Redis data.

## Running the frontend without Docker

```bash
cd frontend
npm install
npm run dev
```

When Vite runs directly on the host, its proxy defaults to `http://127.0.0.1:8000`.

The backend and Redis must also be running on the host in this setup.

## Current database status

PostgreSQL is provisioned and persistent in Docker Compose.

The current application has not yet implemented SQLAlchemy based application persistence. Do not assume users, conversations or tasks are stored in PostgreSQL until those modules are implemented and tested.
