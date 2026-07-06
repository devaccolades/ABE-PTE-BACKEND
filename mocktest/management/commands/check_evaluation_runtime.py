from celery import current_app
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from redis import Redis


class Command(BaseCommand):
    help = "Check runtime dependencies needed for async evaluation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-redis",
            action="store_true",
            help="Skip Redis broker/result backend connectivity checks.",
        )
        parser.add_argument(
            "--skip-celery",
            action="store_true",
            help="Skip Celery worker ping checks.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=3.0,
            help="Connection timeout in seconds for Redis and Celery checks.",
        )

    def handle(self, *args, **options):
        timeout = options["timeout"]
        if timeout <= 0:
            raise CommandError("--timeout must be greater than zero.")

        failures = []

        self.stdout.write("Evaluation runtime check")
        self.stdout.write("========================")

        self._check_openai_settings(failures)

        if not options["skip_redis"]:
            self._check_redis("broker", settings.CELERY_BROKER_URL, timeout, failures)
            self._check_redis(
                "result backend",
                settings.CELERY_RESULT_BACKEND,
                timeout,
                failures,
            )

        if not options["skip_celery"]:
            self._check_celery_workers(timeout, failures)

        if failures:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("Runtime check failed:"))
            for failure in failures:
                self.stdout.write(f"- {failure}")
            raise CommandError("Evaluation runtime is not healthy.")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Evaluation runtime looks healthy."))

    def _check_openai_settings(self, failures):
        self.stdout.write("OpenAI settings")
        self.stdout.write("---------------")

        self._print_secret_presence("OPENAI_API_KEY", settings.OPENAI_API_KEY, failures)
        self._print_secret_presence(
            "OPENAI_WHISPER_API_KEY",
            settings.OPENAI_WHISPER_API_KEY,
            failures,
        )
        self.stdout.write(f"OPENAI_TIMEOUT_SECONDS={settings.OPENAI_TIMEOUT_SECONDS}")
        self.stdout.write(f"OPENAI_MAX_RETRIES={settings.OPENAI_MAX_RETRIES}")
        self.stdout.write(f"OPENAI_EVALUATION_MODEL={settings.OPENAI_EVALUATION_MODEL}")
        self.stdout.write(f"OPENAI_TRANSCRIPTION_MODEL={settings.OPENAI_TRANSCRIPTION_MODEL}")
        self.stdout.write(f"CELERY_TASK_DEFAULT_QUEUE={settings.CELERY_TASK_DEFAULT_QUEUE}")
        self.stdout.write(f"CELERY_EVALUATION_QUEUE={settings.CELERY_EVALUATION_QUEUE}")
        self.stdout.write(f"CELERY_TRANSCRIPTION_QUEUE={settings.CELERY_TRANSCRIPTION_QUEUE}")

    def _print_secret_presence(self, name, value, failures):
        if value:
            self.stdout.write(f"{name}=set")
            return

        self.stdout.write(self.style.ERROR(f"{name}=missing"))
        failures.append(f"{name} is missing")

    def _check_redis(self, label, url, timeout, failures):
        self.stdout.write("")
        self.stdout.write(f"Redis {label}")
        self.stdout.write("-" * (6 + len(label)))
        self.stdout.write(f"url={self._redact_url(url)}")

        try:
            client = Redis.from_url(
                url,
                socket_connect_timeout=timeout,
                socket_timeout=timeout,
            )
            client.ping()
        except Exception as exc:
            self.stdout.write(self.style.ERROR("status=failed"))
            failures.append(f"Redis {label} unavailable: {exc}")
            return

        self.stdout.write(self.style.SUCCESS("status=ok"))

    def _check_celery_workers(self, timeout, failures):
        self.stdout.write("")
        self.stdout.write("Celery workers")
        self.stdout.write("--------------")

        try:
            inspector = current_app.control.inspect(timeout=timeout)
            ping = inspector.ping() or {}
        except Exception as exc:
            self.stdout.write(self.style.ERROR("status=failed"))
            failures.append(f"Celery inspect failed: {exc}")
            return

        if not ping:
            self.stdout.write(self.style.ERROR("workers=0"))
            failures.append("No Celery workers responded to ping")
            return

        self.stdout.write(self.style.SUCCESS(f"workers={len(ping)}"))
        for worker_name in sorted(ping):
            self.stdout.write(f"- {worker_name}: {ping[worker_name]}")

        try:
            active_queues = inspector.active_queues() or {}
        except Exception as exc:
            failures.append(f"Celery active queue inspection failed: {exc}")
            return

        self.stdout.write("")
        self.stdout.write("Worker queues")
        self.stdout.write("-------------")
        expected_queues = {
            settings.CELERY_EVALUATION_QUEUE,
            settings.CELERY_TRANSCRIPTION_QUEUE,
        }
        seen_queues = set()
        for worker_name in sorted(active_queues):
            queue_names = sorted(
                queue.get("name", "")
                for queue in active_queues[worker_name]
                if queue.get("name")
            )
            seen_queues.update(queue_names)
            self.stdout.write(f"- {worker_name}: {', '.join(queue_names) or '-'}")

        missing_queues = expected_queues - seen_queues
        if missing_queues:
            failures.append(
                "No Celery worker is consuming expected queues: "
                + ", ".join(sorted(missing_queues))
            )

    def _redact_url(self, url):
        if "@" not in url:
            return url

        scheme, rest = url.split("://", 1)
        _, host = rest.rsplit("@", 1)
        return f"{scheme}://***@{host}"
