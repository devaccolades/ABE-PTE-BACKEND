import hashlib
import io
import json
import platform
import subprocess
from pathlib import Path

import django
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone


AUDITED_APPS = ("mocktest", "examinor")


class Command(BaseCommand):
    help = (
        "Collect a read-only, secret-safe migration and database schema baseline "
        "for evaluation deployments."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Write the JSON report to this path instead of stdout.",
        )

    def handle(self, *args, **options):
        report = {
            "report_version": 1,
            "generated_at": timezone.now().isoformat(),
            "host": platform.node(),
            "runtime": {
                "python": platform.python_version(),
                "django": django.get_version(),
            },
            "git": self._collect_git(),
            "database": self._collect_database(),
            "migration_files": self._collect_migration_files(),
            "migration_state": self._collect_migration_state(),
            "model_drift": self._capture_management_command(
                "makemigrations",
                *AUDITED_APPS,
                check=True,
                dry_run=True,
                verbosity=1,
            ),
            "migration_plan": self._capture_management_command(
                "migrate",
                plan=True,
                verbosity=1,
            ),
            "schema": self._collect_schema(),
        }

        rendered = json.dumps(report, indent=2, sort_keys=True, default=str)
        output_path = options.get("output")
        if not output_path:
            self.stdout.write(rendered)
            return

        path = Path(output_path).expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            raise CommandError(f"Could not write baseline report: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Baseline report written to {path}"))

    def _collect_git(self):
        commit = self._run_git("rev-parse", "HEAD")
        branch = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        status = self._run_git("status", "--short", "--branch")

        return {
            "commit": commit["stdout"],
            "branch": branch["stdout"],
            "status": status["stdout"].splitlines(),
            "errors": [
                result["error"]
                for result in (commit, branch, status)
                if result["error"]
            ],
        }

    def _run_git(self, *arguments):
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=settings.BASE_DIR,
                capture_output=True,
                check=False,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"stdout": "", "error": str(exc)}

        error = ""
        if result.returncode:
            error = result.stderr.strip() or f"git exited with {result.returncode}"
        return {"stdout": result.stdout.strip(), "error": error}

    def _collect_database(self):
        database = settings.DATABASES[connection.alias]
        return {
            "alias": connection.alias,
            "engine": database.get("ENGINE", ""),
            "vendor": connection.vendor,
            "server_version": self._database_version(),
        }

    def _database_version(self):
        if connection.vendor == "sqlite":
            return getattr(connection.Database, "sqlite_version", "unknown")
        if connection.vendor == "postgresql":
            return getattr(connection, "pg_version", "unknown")
        if connection.vendor == "mysql":
            return getattr(connection, "mysql_version", "unknown")
        return "unknown"

    def _collect_migration_files(self):
        tracked_result = self._run_git(
            "ls-files",
            "--",
            *(f"{app_label}/migrations" for app_label in AUDITED_APPS),
        )
        tracked_paths = set(tracked_result["stdout"].splitlines())
        files = []

        for app_label in AUDITED_APPS:
            migration_dir = Path(apps.get_app_config(app_label).path) / "migrations"
            for path in sorted(migration_dir.glob("*.py")):
                relative_path = self._relative_path(path)
                files.append(
                    {
                        "app": app_label,
                        "name": path.name,
                        "path": relative_path,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "git_tracked": relative_path in tracked_paths,
                    }
                )

        return {
            "files": files,
            "git_error": tracked_result["error"],
        }

    def _relative_path(self, path):
        try:
            return (
                path.resolve()
                .relative_to(Path(settings.BASE_DIR).resolve())
                .as_posix()
            )
        except ValueError:
            return str(path.resolve())

    def _collect_migration_state(self):
        state = {
            "applied": [],
            "disk": [],
            "leaf_nodes": [],
            "unapplied": [],
            "error": "",
        }

        try:
            applied_rows = MigrationRecorder.Migration.objects.filter(
                app__in=AUDITED_APPS
            ).order_by("app", "name")
            state["applied"] = [
                {
                    "app": row.app,
                    "name": row.name,
                    "applied_at": row.applied.isoformat(),
                }
                for row in applied_rows
            ]

            loader = MigrationLoader(connection, ignore_no_migrations=True)
            disk_nodes = sorted(
                node for node in loader.disk_migrations if node[0] in AUDITED_APPS
            )
            applied_nodes = {
                node for node in loader.applied_migrations if node[0] in AUDITED_APPS
            }
            state["disk"] = [self._migration_label(node) for node in disk_nodes]
            state["leaf_nodes"] = [
                self._migration_label(node)
                for node in sorted(loader.graph.leaf_nodes())
                if node[0] in AUDITED_APPS
            ]
            state["unapplied"] = [
                self._migration_label(node)
                for node in disk_nodes
                if node not in applied_nodes
            ]
        except Exception as exc:
            state["error"] = f"{exc.__class__.__name__}: {exc}"

        return state

    def _migration_label(self, node):
        return f"{node[0]}.{node[1]}"

    def _capture_management_command(self, command_name, *args, **options):
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = 0
        error = ""

        try:
            call_command(
                command_name,
                *args,
                stdout=stdout,
                stderr=stderr,
                no_color=True,
                **options,
            )
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        except Exception as exc:
            exit_code = 1
            error = f"{exc.__class__.__name__}: {exc}"

        return {
            "exit_code": exit_code,
            "stdout": stdout.getvalue().strip().splitlines(),
            "stderr": stderr.getvalue().strip().splitlines(),
            "error": error,
        }

    def _collect_schema(self):
        tables = sorted(
            {
                model._meta.db_table
                for app_label in AUDITED_APPS
                for model in apps.get_app_config(app_label).get_models(
                    include_auto_created=True
                )
            }
        )
        schema = {}

        try:
            with connection.cursor() as cursor:
                existing_tables = set(connection.introspection.table_names(cursor))
                for table in tables:
                    schema[table] = self._describe_table(
                        cursor,
                        table,
                        existing_tables,
                    )
        except Exception as exc:
            return {"error": f"{exc.__class__.__name__}: {exc}", "tables": schema}

        return {"error": "", "tables": schema}

    def _describe_table(self, cursor, table, existing_tables):
        if table not in existing_tables:
            return {"exists": False, "columns": [], "constraints": {}}

        columns = []
        for field in connection.introspection.get_table_description(cursor, table):
            columns.append(
                {
                    "name": field.name,
                    "type_code": str(field.type_code),
                    "null_ok": field.null_ok,
                    "default": self._json_safe(field.default),
                }
            )

        constraints = connection.introspection.get_constraints(cursor, table)
        normalized_constraints = {
            name: {
                key: self._json_safe(metadata.get(key))
                for key in (
                    "columns",
                    "primary_key",
                    "unique",
                    "foreign_key",
                    "check",
                    "index",
                    "orders",
                    "type",
                    "condition",
                    "definition",
                )
                if metadata.get(key) is not None
            }
            for name, metadata in sorted(constraints.items())
        }
        return {
            "exists": True,
            "columns": columns,
            "constraints": normalized_constraints,
        }

    def _json_safe(self, value):
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): self._json_safe(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        return str(value)
