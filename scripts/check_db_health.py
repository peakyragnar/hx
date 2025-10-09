from __future__ import annotations

import os
import sys
from contextlib import closing
from typing import Iterable, Tuple


def main() -> int:
    try:
        import psycopg  # type: ignore
    except ModuleNotFoundError:
        print("ERROR: psycopg not available (install dependency)", file=sys.stderr)
        return 1
    url = os.getenv("DATABASE_URL_PROD") or os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL_PROD or DATABASE_URL must be set", file=sys.stderr)
        return 1

    try:
        with closing(psycopg.connect(url, connect_timeout=5)) as conn:
            with conn.cursor() as cur:
                table_stats = collect_counts(cur, ["checks", "result_cache", "usage_ledger"])
                for name, count in table_stats:
                    print(f"{name}_count={count}")

                cur.execute(
                    "SELECT NOW()::timestamptz, "
                    "COALESCE(pg_is_in_recovery(), false)"
                )
                ts, in_recovery = cur.fetchone()
                print(f"timestamp={ts.isoformat()} in_recovery={in_recovery}")
    except Exception as exc:  # pragma: no cover - health script
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 0


def collect_counts(cur: psycopg.Cursor, tables: Iterable[str]) -> list[Tuple[str, int]]:
    stats: list[Tuple[str, int]] = []
    for table in tables:
        cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
        exists = cur.fetchone()[0]
        if not exists:
            stats.append((table, -1))
            continue
        cur.execute(f"SELECT COUNT(*) FROM {table};")
        stats.append((table, cur.fetchone()[0]))
    return stats


if __name__ == "__main__":
    raise SystemExit(main())
