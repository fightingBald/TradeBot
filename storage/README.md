# Storage

This folder contains Alembic migrations for SQLite/Postgres.

## Usage

```bash
alembic upgrade head
```

The default database URL comes from `DATABASE_URL` (see `.env.example`).
