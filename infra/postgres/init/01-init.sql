-- Runs once on first start of the Postgres container.
-- App database (created by POSTGRES_DB) gets pgvector; HAPI gets its own database.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE hapi;
