"""Load the cleaned LCA parquet file(s) into Postgres (Supabase).

Usage (from the repo root, inside .venv):
    python src/load_supabase.py                                   # all data/processed/lca_roles_*.parquet
    python src/load_supabase.py data/processed/lca_roles_fy2026q3.parquet

Reads SUPABASE_DB_URL from .env, creates the table from sql/schema/01_lca_roles.sql if missing,
then upserts on case_number in chunks. Re-running the same file writes nothing (only changed rows
are updated), so the load is idempotent. All files are combined first with clean_lca.combine_quarters
(union, then one row per case_number from the most recent source file by fiscal year/quarter), because DOL
files are not consistently cumulative. In the database, an existing row is only overwritten by a row from
the same or a newer source file, so loading an older file later can't clobber newer data.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_lca import combine_quarters  # noqa: E402
SCHEMA_SQL = ROOT / "sql" / "schema" / "01_lca_roles.sql"
TABLE = "lca_roles"
CHUNK_ROWS = 10_000

INT_COLS = ["decision_fy", "decision_fq", "source_fy", "source_quarter", "total_worker_positions",
            "new_employment", "continued_employment", "change_employer"]
DATE_COLS = ["received_date", "decision_date", "begin_date", "end_date"]
NUM_COLS = ["wage_annual_from", "wage_annual_to", "pw_annual", "wage_vs_pw_pct"]


def get_engine():
    load_dotenv(ROOT / ".env")
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        sys.exit("SUPABASE_DB_URL is not set. Copy .env.example to .env and paste the Session pooler URI.")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return create_engine(url, pool_pre_ping=True)


def table_columns(conn) -> list[str]:
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position"), {"t": TABLE})
    return [r[0] for r in rows if r[0] != "loaded_at"]


def prepare(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        sys.exit(f"Parquet is missing columns the table expects: {missing}")
    df = df[cols].copy()
    for c in INT_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c in DATE_COLS:
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64").round(2)
    if df["case_number"].isna().any():
        sys.exit("Some rows have no case_number.")
    dups = df["case_number"].duplicated(keep="last")
    if dups.any():
        print(f"  dropping {dups.sum():,} duplicate case_number rows (keeping the last)")
        df = df[~dups]
    return df


def upsert(raw_conn, df: pd.DataFrame, cols: list[str]) -> None:
    col_list = ", ".join(cols)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "case_number")
    # Only rewrite rows whose data changed, so re-runs don't bloat the table with dead rows.
    tgt_list = ", ".join(f"{TABLE}.{c}" for c in cols)
    exc_list = ", ".join(f"EXCLUDED.{c}" for c in cols)
    with raw_conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE IF NOT EXISTS _stage (LIKE public.{TABLE} INCLUDING DEFAULTS) ON COMMIT DROP")
        for start in range(0, len(df), CHUNK_ROWS):
            chunk = df.iloc[start:start + CHUNK_ROWS]
            buf = io.StringIO()
            chunk.to_csv(buf, index=False, header=False, na_rep="\\N")
            buf.seek(0)
            cur.execute("TRUNCATE _stage")
            cur.copy_expert(f"COPY _stage ({col_list}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
            cur.execute(
                f"INSERT INTO public.{TABLE} ({col_list}) SELECT {col_list} FROM _stage "
                f"ON CONFLICT (case_number) DO UPDATE SET {updates}, loaded_at = now() "
                f"WHERE ({tgt_list}) IS DISTINCT FROM ({exc_list}) "
                f"AND (EXCLUDED.source_fy, EXCLUDED.source_quarter) >= "
                f"(COALESCE({TABLE}.source_fy, 0), COALESCE({TABLE}.source_quarter, 0))")
            print(f"  upserted rows {start + 1:,}-{start + len(chunk):,}")
    raw_conn.commit()


def main(paths: list[str]) -> None:
    files = [Path(p) for p in paths] or sorted((ROOT / "data" / "processed").glob("lca_roles_*.parquet"))
    if not files:
        sys.exit("No parquet files found in data/processed/. Run notebooks/01_clean_lca.ipynb first.")
    engine = get_engine()
    with engine.begin() as conn:
        conn.exec_driver_sql(SCHEMA_SQL.read_text())
        before = conn.execute(text(f"SELECT count(*) FROM public.{TABLE}")).scalar()
        cols = table_columns(conn)
    print(f"Rows in {TABLE} before: {before:,}")

    frames = []
    for f in files:
        part = pd.read_parquet(f)
        print(f"{f.name}: {len(part):,} rows")
        frames.append(part)
    combined = combine_quarters(frames)
    print(f"Combined: {sum(map(len, frames)):,} rows -> {len(combined):,} unique case_number")
    df = prepare(combined, cols)
    raw = engine.raw_connection()
    try:
        upsert(raw, df, cols)
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()

    with engine.connect() as conn:
        after = conn.execute(text(f"SELECT count(*) FROM public.{TABLE}")).scalar()
        cert = conn.execute(text(f"SELECT count(*) FROM public.{TABLE} WHERE is_certified_h1b")).scalar()
        size = conn.execute(text(f"SELECT pg_size_pretty(pg_total_relation_size('public.{TABLE}'))")).scalar()
        by_fy = conn.execute(text(
            f"SELECT decision_fy, count(*) FROM public.{TABLE} GROUP BY 1 ORDER BY 1")).all()
    print(f"Rows in {TABLE} after: {after:,} (new: {after - before:,}); certified H-1B: {cert:,}")
    print("By decision fiscal year: " + ", ".join(f"FY{fy}: {n:,}" for fy, n in by_fy))
    print(f"Table size incl. indexes: {size} (Supabase free tier: 500 MB)")


if __name__ == "__main__":
    main(sys.argv[1:])
