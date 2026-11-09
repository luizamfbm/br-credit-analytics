"""Thin read-only access to the warehouse: local DuckDB or Snowflake.

The same SQL runs on both, so the summary can be developed locally for free and run
in production on Snowflake. Every query returns a list of tuples.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Warehouse:
    def __init__(self, target: str = "local"):
        self.target = target
        if target == "local":
            import duckdb

            path = os.getenv("DUCKDB_PATH", str(ROOT / "data" / "credito.duckdb"))
            self._con = duckdb.connect(path, read_only=True)
        else:
            sys.path.insert(0, str(ROOT / "ingestion"))
            from load_snowflake_stage import connect  # same key pair as dbt

            database = "CREDITO_REPLAY" if target == "replay" else os.getenv("SNOWFLAKE_DATABASE", "CREDITO")
            self._con = connect(database.lower())

    def query(self, sql: str) -> list[tuple]:
        if self.target == "local":
            return self._con.execute(sql).fetchall()
        cur = self._con.cursor()
        try:
            return cur.execute(sql).fetchall()
        finally:
            cur.close()

    def close(self) -> None:
        self._con.close()
