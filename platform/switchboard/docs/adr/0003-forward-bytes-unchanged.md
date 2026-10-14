# ADR 0003: Forward request bytes unchanged unless policy requires a change

Status: accepted (2026-10-15)

## Context
Prompt caching matches byte-identical prefixes. A gateway that parses JSON and re-serialises it can change key
order, whitespace or escaping, silently turning every cache read into a full-price cache miss.

## Decision
Parse the body to inspect it, but forward the original bytes. Re-serialise only when the gateway must change the
content: PII redaction found something (`pii_mode=redact`), or a fallback model replaces the `model` field.

## Consequences
+ Caching behaves exactly as it would without the gateway. A test asserts byte-for-byte equality.
- Redacted requests lose cache hits for the redacted prefix; prefer redacting at the application edge for prompts
  that must stay cacheable.
