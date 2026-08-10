from celery import current_app
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Min
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from redis import Redis

from mocktest.models import EvaluationOutbox


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
        self._check_scoring_settings(failures)
        self._check_celery_settings(failures)
        self._check_evaluation_outbox(failures)

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

    def _check_scoring_settings(self, failures):
        self.stdout.write("")
        self.stdout.write("Scoring settings")
        self.stdout.write("----------------")
        mode = settings.EVALUATION_SCORING_MODE
        self.stdout.write(f"EVALUATION_SCORING_MODE={mode}")
        if mode not in {"legacy", "shadow", "v2"}:
            failures.append(
                "EVALUATION_SCORING_MODE must be legacy, shadow, or v2"
            )

    def _check_celery_settings(self, failures):
        self.stdout.write("")
        self.stdout.write("Celery durability")
        self.stdout.write("-----------------")
        self.stdout.write(f"CELERY_TASK_ACKS_LATE={settings.CELERY_TASK_ACKS_LATE}")
        self.stdout.write(
            "CELERY_TASK_REJECT_ON_WORKER_LOST="
            f"{settings.CELERY_TASK_REJECT_ON_WORKER_LOST}"
        )
        self.stdout.write(
            "CELERY_WORKER_PREFETCH_MULTIPLIER="
            f"{settings.CELERY_WORKER_PREFETCH_MULTIPLIER}"
        )
        self.stdout.write(f"CELERY_TASK_TRACK_STARTED={settings.CELERY_TASK_TRACK_STARTED}")
        self.stdout.write(
            f"CELERY_TASK_SOFT_TIME_LIMIT={settings.CELERY_TASK_SOFT_TIME_LIMIT}"
        )
        self.stdout.write(f"CELERY_TASK_TIME_LIMIT={settings.CELERY_TASK_TIME_LIMIT}")
        self.stdout.write(
            "CELERY_VISIBILITY_TIMEOUT_SECONDS="
            f"{settings.CELERY_BROKER_TRANSPORT_OPTIONS['visibility_timeout']}"
        )
        self.stdout.write(
            f"EVALUATION_ENGINE_VERSION={settings.EVALUATION_ENGINE_VERSION}"
        )
        self.stdout.write(
            f"EVALUATION_JOB_LEASE_SECONDS={settings.EVALUATION_JOB_LEASE_SECONDS}"
        )
        self.stdout.write(
            f"EVALUATION_OUTBOX_BATCH_SIZE={settings.EVALUATION_OUTBOX_BATCH_SIZE}"
        )
        self.stdout.write(
            "EVALUATION_OUTBOX_INTERVAL_SECONDS="
            f"{settings.EVALUATION_OUTBOX_INTERVAL_SECONDS}"
        )
        self.stdout.write(
            f"EVALUATION_OUTBOX_STALE_SECONDS={settings.EVALUATION_OUTBOX_STALE_SECONDS}"
        )
        self.stdout.write(
            "EVALUATION_OUTBOX_RETRY_BASE_SECONDS="
            f"{settings.EVALUATION_OUTBOX_RETRY_BASE_SECONDS}"
        )
        self.stdout.write(
            "EVALUATION_OUTBOX_RETRY_MAX_SECONDS="
            f"{settings.EVALUATION_OUTBOX_RETRY_MAX_SECONDS}"
        )

        if not settings.CELERY_TASK_ACKS_LATE:
            failures.append("CELERY_TASK_ACKS_LATE must be enabled")
        if not settings.CELERY_TASK_REJECT_ON_WORKER_LOST:
            failures.append("CELERY_TASK_REJECT_ON_WORKER_LOST must be enabled")
        if settings.CELERY_WORKER_PREFETCH_MULTIPLIER != 1:
            failures.append("CELERY_WORKER_PREFETCH_MULTIPLIER must be 1")
        if settings.CELERY_TASK_SOFT_TIME_LIMIT >= settings.CELERY_TASK_TIME_LIMIT:
            failures.append("Celery soft time limit must be lower than the hard time limit")
        if settings.EVALUATION_JOB_LEASE_SECONDS < settings.CELERY_TASK_TIME_LIMIT:
            failures.append(
                "Evaluation job lease must be at least the Celery hard time limit"
            )
        if settings.EVALUATION_OUTBOX_BATCH_SIZE < 1:
            failures.append("EVALUATION_OUTBOX_BATCH_SIZE must be at least 1")
        if settings.EVALUATION_OUTBOX_INTERVAL_SECONDS <= 0:
            failures.append("EVALUATION_OUTBOX_INTERVAL_SECONDS must be positive")
        if settings.EVALUATION_OUTBOX_STALE_SECONDS < settings.EVALUATION_OUTBOX_INTERVAL_SECONDS:
            failures.append(
                "Evaluation outbox stale threshold must be at least its dispatch interval"
            )
        if settings.EVALUATION_OUTBOX_RETRY_BASE_SECONDS < 1:
            failures.append("Evaluation outbox retry base must be at least 1 second")
        if (
            settings.EVALUATION_OUTBOX_RETRY_MAX_SECONDS
            < settings.EVALUATION_OUTBOX_RETRY_BASE_SECONDS
        ):
            failures.append(
                "Evaluation outbox retry maximum must be at least its retry base"
            )

    def _check_evaluation_outbox(self, failures):
        self.stdout.write("")
        self.stdout.write("Evaluation outbox")
        self.stdout.write("-----------------")
        try:
            unpublished = EvaluationOutbox.objects.filter(published_at__isnull=True)
            count = unpublished.count()
            failed_count = unpublished.exclude(last_error="").count()
            oldest = unpublished.aggregate(value=Min("created_at"))["value"]
        except (OperationalError, ProgrammingError):
            self.stdout.write("status=unavailable")
            failures.append(
                "Evaluation outbox table is unavailable; apply pending migrations"
            )
            return

        self.stdout.write(f"unpublished={count}")
        self.stdout.write(f"with_publish_error={failed_count}")
        if oldest is None:
            self.stdout.write("oldest_age_seconds=0")
            return

        age_seconds = max(0, int((timezone.now() - oldest).total_seconds()))
        self.stdout.write(f"oldest_age_seconds={age_seconds}")
        if age_seconds > settings.EVALUATION_OUTBOX_STALE_SECONDS:
            failures.append(
                f"Evaluation outbox has unpublished work older than "
                f"{settings.EVALUATION_OUTBOX_STALE_SECONDS} seconds"
            )

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
