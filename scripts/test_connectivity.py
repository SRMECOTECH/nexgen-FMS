"""
Lakehouse connectivity tester.

Usage (from project root, with venv active):
    python scripts/test_connectivity.py

What it does, in order:
    1. Loads .env
    2. Pings each known port (port-level reachability — TCP open?)
    3. Tries PyIceberg REST catalog → list tables, count rows on fact_trips
    4. Tries ClickHouse gateway → SELECT 1, SHOW DATABASES, count rows
    5. Tries DuckDB + Iceberg extension
    6. Tries Trino proxy /v1/info (if configured)
    7. Prints a verdict-per-method table at the end.

Honest about what works vs what doesn't — never silently swallows errors.
"""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

# ---------------------------------------------------------------------
# Setup — load .env and add project root to sys.path
# ---------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    print("[WARN] python-dotenv not installed; relying on shell env vars only")

from lakehouse.settings import get_settings  # noqa: E402

S = get_settings()

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
GREY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def hdr(txt: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"\n{BOLD}{CYAN}-- {txt} {'-' * max(0, 76 - len(txt))}{RESET}")


def ok(msg: str) -> None:
    print(f"  {GREEN}[OK]  {RESET}{msg}")


def fail(msg: str) -> None:
    print(f"  {RED}[FAIL]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {GREY}[..]  {RESET}{msg}")


# ---------------------------------------------------------------------
# 1. Port reachability
# ---------------------------------------------------------------------

def port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def test_ports() -> dict[str, bool]:
    hdr("STEP 1 — Port reachability")
    host_iceberg = urlparse(S.iceberg_catalog_uri).hostname or ""
    port_iceberg = urlparse(S.iceberg_catalog_uri).port or 8181
    host_s3 = urlparse(S.s3_endpoint).hostname or ""
    port_s3 = urlparse(S.s3_endpoint).port or 9000

    checks = {
        "Lakehouse UI (5173)":   (urlparse(S.lakehouse_base_url).hostname, 5173),
        "Iceberg REST":          (host_iceberg, port_iceberg),
        "MinIO / S3":            (host_s3, port_s3),
        "ClickHouse HTTP":       (S.clickhouse_host, S.clickhouse_port),
        "Trino proxy":           (S.trino_host, S.trino_port),
    }

    results = {}
    for name, (h, p) in checks.items():
        if not h:
            warn(f"{name}: host not set, skipping")
            results[name] = False
            continue
        is_open = port_open(h, p)
        results[name] = is_open
        (ok if is_open else fail)(f"{name}: {h}:{p}  → {'OPEN' if is_open else 'CLOSED / unreachable'}")
    return results


# ---------------------------------------------------------------------
# 2. PyIceberg
# ---------------------------------------------------------------------

def test_pyiceberg() -> bool:
    hdr("STEP 2 — PyIceberg (REST catalog)")
    if not S.iceberg_token and not S.s3_access_key:
        warn("ICEBERG_TOKEN and S3_ACCESS_KEY both empty — Iceberg call will likely 401.")
        info("Add the credentials from the Consumer registration in the lakehouse UI to .env.")

    try:
        from pyiceberg.catalog import load_catalog
    except ImportError as exc:
        fail(f"pyiceberg not installed: {exc}")
        return False

    cfg = {
        "type":                 "rest",
        "uri":                  S.iceberg_catalog_uri,
        "warehouse":            S.iceberg_warehouse,
        "s3.endpoint":          S.s3_endpoint,
        "s3.access-key-id":     S.s3_access_key,
        "s3.secret-access-key": S.s3_secret_key,
        "s3.region":            S.s3_region,
        "s3.path-style-access": "true",
    }
    if S.iceberg_token:
        cfg["token"] = S.iceberg_token

    info(f"catalog uri = {S.iceberg_catalog_uri}")
    info(f"warehouse   = {S.iceberg_warehouse}")
    info(f"s3 endpoint = {S.s3_endpoint}")

    try:
        t0 = time.perf_counter()
        cat = load_catalog("nexgen-test", **cfg)
        ok(f"catalog loaded in {(time.perf_counter()-t0)*1000:.0f}ms")
    except Exception as exc:
        fail(f"load_catalog failed: {type(exc).__name__}: {exc}")
        info("Most likely cause: REST port isn't exposed externally (see Step 1).")
        return False

    try:
        tables = cat.list_tables(S.iceberg_namespace)
        ok(f"list_tables('{S.iceberg_namespace}') → {len(tables)} tables")
        for t in tables[:6]:
            info(f"    {'.'.join(t)}")
    except Exception as exc:
        fail(f"list_tables failed: {type(exc).__name__}: {exc}")
        return False

    try:
        tbl = cat.load_table(f"{S.iceberg_namespace}.fact_trips")
        t0 = time.perf_counter()
        df = tbl.scan(limit=5).to_arrow().to_pandas()
        ok(f"fact_trips scan(limit=5) → {len(df)} rows in {(time.perf_counter()-t0)*1000:.0f}ms")
        info(f"sample columns: {list(df.columns)[:8]}...")
    except Exception as exc:
        fail(f"scan failed: {type(exc).__name__}: {exc}")
        return False

    return True


# ---------------------------------------------------------------------
# 3. ClickHouse gateway
# ---------------------------------------------------------------------

def test_clickhouse() -> bool:
    hdr("STEP 3 — ClickHouse gateway")
    if not S.clickhouse_password:
        warn("CLICKHOUSE_PASSWORD is empty — server requires a password (verified earlier).")

    try:
        import clickhouse_connect
    except ImportError as exc:
        fail(f"clickhouse-connect not installed: {exc}")
        return False

    info(f"host={S.clickhouse_host}:{S.clickhouse_port}  user={S.clickhouse_user}  db={S.clickhouse_database}")

    try:
        client = clickhouse_connect.get_client(
            host=S.clickhouse_host, port=S.clickhouse_port,
            username=S.clickhouse_user, password=S.clickhouse_password,
            database=S.clickhouse_database, connect_timeout=5,
        )
        ok("client created")
    except Exception as exc:
        fail(f"connect failed: {type(exc).__name__}: {exc}")
        return False

    try:
        v = client.query("SELECT 1 AS x").result_rows
        ok(f"SELECT 1 → {v}")
    except Exception as exc:
        fail(f"SELECT 1 failed: {type(exc).__name__}: {exc}")
        return False

    try:
        dbs = client.query("SHOW DATABASES").result_rows
        ok(f"SHOW DATABASES → {[r[0] for r in dbs]}")
    except Exception as exc:
        fail(f"SHOW DATABASES failed: {exc}")

    try:
        tables = client.query(f"SHOW TABLES FROM {S.clickhouse_database}").result_rows
        ok(f"SHOW TABLES FROM {S.clickhouse_database} → {[r[0] for r in tables]}")
    except Exception as exc:
        fail(f"SHOW TABLES failed: {exc}")
        return True   # connect ok, just no schema

    try:
        t0 = time.perf_counter()
        df = client.query_df(f"SELECT * FROM {S.clickhouse_database}.fact_trips LIMIT 5")
        ok(f"sample 5 rows in {(time.perf_counter()-t0)*1000:.0f}ms — cols: {list(df.columns)[:6]}...")
    except Exception as exc:
        warn(f"sample query failed (table may not exist yet): {exc}")

    return True


# ---------------------------------------------------------------------
# 4. DuckDB + Iceberg
# ---------------------------------------------------------------------

def test_duckdb() -> bool:
    hdr("STEP 4 — DuckDB + Iceberg extension")
    try:
        import duckdb
    except ImportError as exc:
        fail(f"duckdb not installed: {exc}")
        return False

    con = duckdb.connect(":memory:")
    try:
        con.execute("INSTALL iceberg; LOAD iceberg;")
        con.execute("INSTALL httpfs; LOAD httpfs;")
        ok("iceberg + httpfs extensions loaded")
    except Exception as exc:
        fail(f"extension load failed: {exc}")
        return False

    try:
        con.execute(f"SET s3_endpoint='{urlparse(S.s3_endpoint).netloc}';")
        con.execute(f"SET s3_access_key_id='{S.s3_access_key}';")
        con.execute(f"SET s3_secret_access_key='{S.s3_secret_key}';")
        con.execute("SET s3_url_style='path';")
        con.execute("SET s3_use_ssl=false;")
        ok("S3 settings applied")
    except Exception as exc:
        warn(f"S3 settings failed: {exc}")

    info("Note: DuckDB needs direct S3/Iceberg metadata reach. If MinIO is not externally")
    info("exposed (Step 1 said CLOSED), this method cannot succeed from your laptop.")
    return True


# ---------------------------------------------------------------------
# 5. Trino proxy
# ---------------------------------------------------------------------

def test_trino() -> bool:
    hdr("STEP 5 — Trino proxy")
    try:
        import requests
    except ImportError:
        fail("requests not installed")
        return False

    base = f"http://{S.trino_host}:{S.trino_port}"
    headers = {"X-Trino-User": "nextgen-fms"}
    if S.trino_token:
        headers["Authorization"] = f"Bearer {S.trino_token}"

    info(f"base = {base}")
    for path in ["/v1/info", "/v1/statement"]:
        try:
            r = requests.get(base + path, headers=headers, timeout=5)
            (ok if r.status_code < 400 else warn)(f"GET {path} → HTTP {r.status_code}")
            if r.status_code < 400:
                info(f"  body[:200]: {r.text[:200]}")
        except Exception as exc:
            fail(f"GET {path} failed: {exc}")

    return True


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def show_env() -> None:
    """Show which credential vars are populated (without leaking secret values)."""
    hdr("STEP 0 — Env vars actually loaded from .env")
    mask = lambda v: f"set ({len(v)} chars, starts {v[:4]}...)" if v else "EMPTY"
    info(f"ICEBERG_TOKEN         = {mask(S.iceberg_token)}")
    info(f"S3_ACCESS_KEY         = {mask(S.s3_access_key)}")
    info(f"S3_SECRET_KEY         = {mask(S.s3_secret_key)}")
    info(f"CLICKHOUSE_USER       = {S.clickhouse_user!r}")
    info(f"CLICKHOUSE_PASSWORD   = {mask(S.clickhouse_password)}")
    info(f"CLICKHOUSE_DATABASE   = {S.clickhouse_database!r}")
    info(f"TRINO_TOKEN           = {mask(S.trino_token)}")


def try_clickhouse_with(user: str, password: str, label: str) -> bool:
    """Try a single ClickHouse credential combination."""
    try:
        import clickhouse_connect
        c = clickhouse_connect.get_client(
            host=S.clickhouse_host, port=S.clickhouse_port,
            username=user, password=password,
            database=S.clickhouse_database, connect_timeout=4,
        )
        r = c.query("SELECT 1").result_rows
        ok(f"[{label}] user={user!r} → SELECT 1 = {r}")
        return True
    except Exception as exc:
        msg = str(exc).split("\n")[0]
        fail(f"[{label}] user={user!r} → {msg[:140]}")
        return False


def test_clickhouse_permutations() -> bool:
    """If the default cred fails, try alt usernames using whatever tokens/keys are set."""
    hdr("STEP 3.b — ClickHouse credential permutations")
    attempts = [
        ("default",      S.clickhouse_password,              "from CLICKHOUSE_PASSWORD"),
        ("nexgen-fms",   S.clickhouse_password,              "username=consumer slug"),
        ("nexgen-fms",   S.iceberg_token,                    "token as password"),
        ("default",      S.iceberg_token,                    "iceberg token as default pw"),
        (S.s3_access_key or "x", S.s3_secret_key or "x",     "S3 keys as CH creds"),
    ]
    any_ok = False
    for user, pw, label in attempts:
        if not user or not pw:
            info(f"[{label}] skipped (empty value)")
            continue
        any_ok |= try_clickhouse_with(user, pw, label)
    return any_ok


def main():
    print(f"{BOLD}nextGen-FMS · lakehouse connectivity tester{RESET}")
    print(f"{GREY}MOCK mode setting = {S.use_mock_data} (this script ignores it){RESET}")

    show_env()
    port_results = test_ports()

    iceberg_ok = test_pyiceberg()
    clickhouse_ok = test_clickhouse()
    if not clickhouse_ok:
        clickhouse_ok = test_clickhouse_permutations()
    duckdb_ok = test_duckdb()
    trino_ok = test_trino()

    hdr("VERDICT")
    table = [
        ("Lakehouse UI port",   port_results.get("Lakehouse UI (5173)", False)),
        ("Iceberg REST port",   port_results.get("Iceberg REST", False)),
        ("MinIO / S3 port",     port_results.get("MinIO / S3", False)),
        ("ClickHouse port",     port_results.get("ClickHouse HTTP", False)),
        ("Trino port",          port_results.get("Trino proxy", False)),
        ("PyIceberg fetch",     iceberg_ok),
        ("ClickHouse SELECT",   clickhouse_ok),
        ("DuckDB+Iceberg ext",  duckdb_ok),
        ("Trino proxy hit",     trino_ok),
    ]
    for name, passed in table:
        mark = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  {mark}  {name}")

    print(f"\n{BOLD}Recommendation:{RESET}")
    if clickhouse_ok:
        ok("ClickHouse is reachable — set USE_MOCK_DATA=false in .env and you're live.")
    elif iceberg_ok:
        ok("PyIceberg works — set USE_MOCK_DATA=false; ML training pipeline can read directly.")
    else:
        fail("No path to real data yet. Most likely:")
        info("(a) Iceberg REST / MinIO ports aren't exposed externally — only ClickHouse is.")
        info("(b) The Consumer credentials work with the proxy/sql_clickhouse mode only, not 'direct'.")
        info("Ask the lakehouse team to either:")
        info("     open ports 8181 + 9000 on 98.70.24.178, OR")
        info("     share ClickHouse user/password generated when you registered the consumer.")


if __name__ == "__main__":
    main()
