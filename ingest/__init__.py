"""Fetch NBA feeds and write the compact tables in SCHEMA.md."""

from ingest.pipeline import BackfillResult, run_backfill

__all__ = ["BackfillResult", "run_backfill"]
