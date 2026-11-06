"""Offline checks for migration safeguards; no database credentials required."""

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location(
    "migrate_to_neon", Path(__file__).resolve().parents[1] / "scripts/migrate_to_neon.py"
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

SOURCE = "postgresql://source:secret@source.example/postgres"
TARGET = "postgresql://owner:secret@ep-example.us-west-2.aws.neon.tech/neondb?sslmode=require"


class MigrationSafetyTests(unittest.TestCase):
    def test_restore_keeps_existing_public_schema_and_all_application_objects(self):
        toc = (b"5; 2615 2200 SCHEMA - public pg_database_owner\n"
               b"6; 3079 1 EXTENSION - vector owner\n"
               b"7; 1259 2 TABLE public grants owner\n"
               b"8; 1259 3 INDEX public grants_embedding_idx owner\n")
        restored = migration.restore_list(toc)
        self.assertNotIn(b"SCHEMA - public", restored)
        self.assertIn(b"EXTENSION - vector", restored)
        self.assertIn(b"TABLE public grants", restored)
        self.assertIn(b"INDEX public grants_embedding_idx", restored)

    def test_rejects_pooled_or_unencrypted_target_before_connecting(self):
        for target in (TARGET.replace("ep-example.", "ep-example-pooler."),
                       TARGET.replace("?sslmode=require", ""), SOURCE):
            with self.subTest(target=target), patch.object(migration.psycopg, "connect") as connect:
                with self.assertRaises(ValueError):
                    migration.migrate(SOURCE, target, copy=True)
                connect.assert_not_called()

    def test_refuses_to_overwrite_existing_target(self):
        source, target = MagicMock(), MagicMock()
        source.execute.return_value.fetchall.return_value = [("vector", "public")]
        with patch.object(migration.psycopg, "connect") as connect, \
             patch.object(migration, "tables", side_effect=[["grants", "user_work"], ["existing"]]), \
             patch.object(migration, "run_pg") as run_pg:
            connect.return_value.__enter__.side_effect = [source, target]
            with self.assertRaisesRegex(RuntimeError, "must be empty"):
                migration.migrate(SOURCE, TARGET, copy=True)
            run_pg.assert_not_called()
            target.execute.assert_not_called()

    def test_supabase_transaction_pooler_uses_session_port_for_dump(self):
        source_url = "postgresql://source:secret@aws-0-us-west-1.pooler.supabase.com:6543/postgres"
        with patch.object(migration.psycopg, "connect", side_effect=RuntimeError("stop before connecting")) as connect:
            with self.assertRaisesRegex(RuntimeError, "stop before connecting"):
                migration.migrate(source_url, TARGET)
            self.assertEqual(migration.conninfo_to_dict(connect.call_args.args[0])["port"], "5432")

    def test_preflight_does_not_write_target_or_run_dump(self):
        source, target = MagicMock(), MagicMock()
        source.execute.return_value.fetchall.return_value = [("vector", "public")]
        with patch.object(migration.psycopg, "connect") as connect, \
             patch.object(migration, "tables", side_effect=[["grants", "user_work"], []]), \
             patch.object(migration, "fingerprint", return_value=(2, "hash")), \
             patch.object(migration, "run_pg") as run_pg, patch("builtins.print"):
            connect.return_value.__enter__.side_effect = [source, target]
            migration.migrate(SOURCE, TARGET)
            target.execute.assert_not_called()
            run_pg.assert_not_called()
            source.execute.assert_any_call("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")

    def test_password_is_not_passed_in_process_arguments_or_errors(self):
        result = subprocess.CompletedProcess([], 1, stderr=b"secret database credentials")
        with patch.object(migration, "pg_tool", return_value="pg_dump"), \
             patch.object(migration.subprocess, "run", return_value=result) as run:
            with self.assertRaises(RuntimeError) as error:
                migration.run_pg("pg_dump", SOURCE, ["--format=custom"])
            self.assertNotIn("secret", str(error.exception))
            self.assertNotIn(SOURCE, run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs["env"]["PGDATABASE"], "postgres")
            self.assertEqual(run.call_args.kwargs["env"]["PGPASSWORD"], "secret")
            self.assertEqual(run.call_args.kwargs["env"]["PGHOST"], "source.example")
            self.assertIn("--no-password", run.call_args.args[0])

    def test_fingerprints_detect_changed_rows_and_ignore_row_order(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.__iter__.return_value = iter([("aaa",), ("bbb",)])
        first = migration.fingerprint(connection, "grants")
        cursor.__iter__.return_value = iter([("bbb",), ("aaa",)])
        self.assertEqual(first, migration.fingerprint(connection, "grants"))
        cursor.__iter__.return_value = iter([("aaa",), ("ccc",)])
        self.assertNotEqual(first, migration.fingerprint(connection, "grants"))


if __name__ == "__main__":
    unittest.main()
