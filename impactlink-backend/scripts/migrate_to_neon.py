"""Copy the application schema to an empty Neon database; leave the source intact.

Run from any directory with the backend virtualenv. Default: inspect only.
Use --copy while application writes are stopped, then switch DATABASE_URL only
after verification succeeds. Connection strings are read from environment/.env
and never passed on the command line.
"""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


BACKEND = Path(__file__).resolve().parents[1]


def pg_tool(name):
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted(
        Path("C:/Program Files/PostgreSQL").glob(f"*/bin/{name}.exe"),
        key=lambda p: int(p.parents[1].name), reverse=True,
    )
    if candidates:
        return str(candidates[0])
    raise RuntimeError(f"Install PostgreSQL client tools and add {name} to PATH.")


def tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
    )]


def fingerprint(conn, table):
    digest = hashlib.sha256()
    # Sort fixed-size row hashes so row order and query plans do not matter.
    query = sql.SQL("SELECT md5(row_to_json(t)::text) FROM public.{} AS t").format(
        sql.Identifier(table)
    )
    with conn.cursor(name="migration_verify") as cur:
        cur.execute(query)
        hashes = sorted(row[0] for row in cur)
    for value in hashes:
        digest.update(value.encode("ascii"))
    return len(hashes), digest.hexdigest()


def run_pg(tool, url, args):
    env = os.environ.copy()
    # Set individual libpq variables: a URI in PGDATABASE is not reliably
    # expanded by client tools. Never prompt or put the password in argv.
    parameters = conninfo_to_dict(url)
    variable_names = {
        "host": "PGHOST", "hostaddr": "PGHOSTADDR", "port": "PGPORT",
        "user": "PGUSER", "password": "PGPASSWORD", "dbname": "PGDATABASE",
        "sslmode": "PGSSLMODE", "channel_binding": "PGCHANNELBINDING",
        "options": "PGOPTIONS", "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY",
        "sslrootcert": "PGSSLROOTCERT", "target_session_attrs": "PGTARGETSESSIONATTRS",
    }
    for parameter, variable in variable_names.items():
        env.pop(variable, None)
        if parameter in parameters:
            env[variable] = parameters[parameter]
    env["PGCONNECT_TIMEOUT"] = "15"
    result = subprocess.run([pg_tool(tool), "--no-password", *args], env=env, capture_output=True, timeout=300)
    if result.returncode:
        # Driver/tool errors may include credentials. Keep them out of logs.
        raise RuntimeError(f"{tool} failed (exit {result.returncode}); connection details suppressed.")
    return result.stdout


def restore_list(contents):
    """Keep the target's existing public schema while restoring its contents."""
    return b"\n".join(line for line in contents.splitlines() if b" SCHEMA - public " not in line) + b"\n"


def migrate(source_url, target_url, copy=False):
    source_info = conninfo_to_dict(source_url)
    # Supabase's transaction pooler cannot safely run pg_dump. The same
    # credentials on port 5432 use its session pooler (also works over IPv4).
    if source_info.get("host", "").endswith(".pooler.supabase.com") and source_info.get("port") == "6543":
        source_url = make_conninfo(source_url, port="5432")
    target_info = conninfo_to_dict(target_url)
    host = target_info.get("host", "")
    if not host.endswith(".neon.tech") or "-pooler" in host:
        raise ValueError("NEON_DATABASE_URL must use a direct, non-pooled Neon hostname.")
    if target_info.get("sslmode") not in ("require", "verify-ca", "verify-full"):
        raise ValueError("Add sslmode=require to NEON_DATABASE_URL.")
    if source_info.get("host") == host:
        raise ValueError("Source and target must be separate database servers.")

    with psycopg.connect(source_url, connect_timeout=15) as source:
        source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        source_tables = tables(source)
        if not {"grants", "user_work"}.issubset(source_tables):
            raise RuntimeError("Source is missing expected ImpactLink tables.")
        extensions = source.execute(
            "SELECT e.extname, n.nspname FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'"
        ).fetchall()
        if not extensions:
            raise RuntimeError("Source is missing the vector extension.")
        with psycopg.connect(target_url, connect_timeout=15) as target:
            if tables(target):
                raise RuntimeError("Target public schema must be empty; no existing tables will be overwritten.")
            baseline = {name: fingerprint(source, name) for name in source_tables}
            for name, (count, _) in baseline.items():
                print(f"Source public.{name}: {count} rows")
            if not copy:
                print("Preflight passed. Stop backend writes, then rerun with --copy.")
                return

            # Confirm tool availability before making any target changes.
            pg_tool("pg_dump")
            pg_tool("pg_restore")
            snapshot = source.execute("SELECT pg_export_snapshot()").fetchone()[0]
            with tempfile.TemporaryDirectory(prefix="impactlink-neon-") as directory:
                archive = str(Path(directory) / "application.dump")
                run_pg("pg_dump", source_url, [
                    "--format=custom", "--schema=public", "--no-owner", "--no-privileges",
                    f"--snapshot={snapshot}", f"--file={archive}",
                ])
                # pg_dump --schema=public omits vector when Supabase installed it
                # in extensions. Preserve its schema so restored vector types resolve.
                for extension, schema in extensions:
                    target.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
                    target.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS {} WITH SCHEMA {}").format(
                        sql.Identifier(extension), sql.Identifier(schema)))
                target.commit()
                # Neon already has public; pg_dump includes CREATE SCHEMA public.
                # Exclude only that definition, retaining all tables and indexes.
                toc = run_pg("pg_restore", target_url, ["--list", archive])
                toc_path = Path(directory) / "restore.list"
                toc_path.write_bytes(restore_list(toc))
                run_pg("pg_restore", target_url, [
                    "--no-owner", "--no-privileges", "--exit-on-error", "--single-transaction",
                    f"--use-list={toc_path}", "--dbname=", archive,
                ])
            if tables(target) != source_tables:
                raise RuntimeError("Restored table list differs from source. Do not switch DATABASE_URL.")
            for name, expected in baseline.items():
                if fingerprint(target, name) != expected:
                    raise RuntimeError(f"Verification failed for {name}. Do not switch DATABASE_URL.")
                print(f"Verified public.{name}: {expected[0]} rows and matching contents")
            # Supabase may install vector outside public. Persist the search path
            # for new runtime connections and apply it to this verification session.
            schemas = ["public", *[schema for _, schema in extensions if schema != "public"]]
            search_path = sql.SQL(", ").join(sql.Identifier(schema) for schema in schemas)
            role, database = target.execute("SELECT current_user, current_database()").fetchone()
            target.execute(sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path TO {}").format(
                sql.Identifier(role), sql.Identifier(database), search_path))
            target.execute(sql.SQL("SET search_path TO {}").format(search_path))
            # Verify application-style unqualified pgvector casts/searches.
            target.execute("SELECT embedding <=> embedding FROM public.grants WHERE embedding IS NOT NULL LIMIT 1")
            target.commit()
            print("Migration verified. Update local and deployed DATABASE_URL, then restart the backend.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy", action="store_true", help="Copy into the empty Neon database after stopping backend writes")
    args = parser.parse_args()
    config = {**dotenv_values(BACKEND / ".env"), **os.environ}
    source = config.get("SUPABASE_DATABASE_URL") or config.get("DATABASE_URL")
    target = config.get("NEON_DATABASE_URL")
    if not source or not target:
        parser.error("Set DATABASE_URL (source) and NEON_DATABASE_URL (target) in backend .env.")
    try:
        migrate(source, target, args.copy)
    except (psycopg.Error, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        # psycopg exceptions can include connection strings or row contents.
        message = type(exc).__name__ if isinstance(exc, (psycopg.Error, subprocess.TimeoutExpired)) else str(exc)
        parser.exit(1, f"Migration stopped: {message}\n")


if __name__ == "__main__":
    main()
