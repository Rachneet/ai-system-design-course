# ADR 0001: Postgres for metadata and skill packages

Status: accepted (2026-10-15)

## Context
Atlas stores versioned artifacts (server.json documents, agent cards, skill frontmatter), their check findings, an
audit log, and skill packages (zips, capped at 10 MB unpacked). Reads are catalog lookups and search; writes are rare.

## Decision
Postgres 16 holds everything, including skill packages as `bytea`. Search uses a generated, weighted `tsvector`
(name and title over description over tags) with a GIN index. Schema changes are Alembic migrations.

## Consequences
+ One transaction covers the artifact, its findings and the audit entry, so the catalog can never show an artifact
  whose checks were not recorded.
+ No vector store or search cluster to run; full-text search with ranking covers a catalog of thousands.
- Packages in the database make backups larger. Move them to object storage (keyed by digest) if the catalog passes
  a few GB, keeping the digest in Postgres as the source of truth.
- Semantic search over descriptions (embeddings, as in the course's Relay retrieval) is a later addition.
