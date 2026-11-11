"""PostgreSQL connection helpers."""

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env.")
    return url


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url())
