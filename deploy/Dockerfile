FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY requirements.txt pyproject.toml ./
RUN uv pip install --system -r requirements.txt

COPY . .
