import re
import shutil
import time

from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from videos.models import Video


class Command(BaseCommand):

    help = "Safely clean up old HLS temporary, backup and orphan directories."

    DIRECTORY_PATTERN = re.compile(
        r"^(?P<video_id>\d+)\.(?P<kind>tmp|old)-(?P<token>[0-9a-f]{32})$"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually delete eligible directories.",
        )

        parser.add_argument(
            "--older-than-hours",
            type=float,
            default=24,
            help="Only clean directories older than this many hours.",
        )

    @staticmethod
    def get_age_hours(path):
        age_seconds = time.time() - path.stat().st_mtime
        return age_seconds / 3600

    @staticmethod
    def is_valid_hls_output(directory):
        """
        Check whether an HLS directory has a valid playlist
        and all referenced media segments exist.
        """

        playlist = directory / "index.m3u8"

        if not playlist.is_file():
            return False

        try:
            lines = playlist.read_text(
                encoding="utf-8"
            ).splitlines()

        except (OSError, UnicodeError):
            return False

        if "#EXTM3U" not in lines:
            return False

        segment_entries = [
            line.strip()
            for line in lines
            if line.strip() and not line.startswith("#")
        ]

        if not segment_entries:
            return False

        for entry in segment_entries:
            relative_path = PurePosixPath(entry)

            if (
                relative_path.is_absolute()
                or ".." in relative_path.parts
            ):
                return False

            segment_path = directory.joinpath(
                *relative_path.parts
            )

            if not segment_path.is_file():
                return False

        return True

    def handle(self, *args, **options):

        execute = options["execute"]
        older_than_hours = options["older_than_hours"]

        if older_than_hours <= 0:
            raise CommandError(
                "--older-than-hours must be greater than zero."
            )

        hls_root = Path(settings.MEDIA_ROOT) / "hls"

        if not hls_root.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"HLS directory does not exist: {hls_root}"
                )
            )
            return

        if hls_root.is_symlink() or not hls_root.is_dir():
            raise CommandError(
                "HLS root must be a regular directory."
            )

        existing_video_ids = set(
            Video.objects.values_list("id", flat=True)
        )

        candidates = []

        self.stdout.write(
            f"\nHLS directory: {hls_root}"
        )

        self.stdout.write(
            f"Age threshold: {older_than_hours} hours"
        )

        self.stdout.write(
            "\nScanning HLS directories...\n"
        )

        for directory in sorted(hls_root.iterdir()):

            if directory.is_symlink():
                self.stdout.write(
                    self.style.WARNING(
                        f"[KEEP] Symlink: {directory.name}"
                    )
                )
                continue

            if not directory.is_dir():
                self.stdout.write(
                    f"[KEEP] Non-directory entry: {directory.name}"
                )
                continue

            age_hours = self.get_age_hours(directory)

            match = self.DIRECTORY_PATTERN.fullmatch(
                directory.name
            )

            # Temporary and backup directories.
            if match:
                video_id = int(match.group("video_id"))
                directory_type = match.group("kind")

                if age_hours < older_than_hours:
                    self.stdout.write(
                        f"[KEEP] Recent {directory_type}: "
                        f"{directory.name} ({age_hours:.1f}h)"
                    )
                    continue

                if directory_type == "tmp":
                    candidates.append(
                        (directory, "temporary", video_id)
                    )
                    continue

                output_dir = hls_root / str(video_id)

                if self.is_valid_hls_output(output_dir):
                    candidates.append(
                        (directory, "backup", video_id)
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[KEEP] Backup preserved because "
                            f"main HLS output is missing or invalid: "
                            f"{directory.name}"
                        )
                    )

                continue

            # Normal directories named with a video ID.
            if directory.name.isdigit():
                video_id = int(directory.name)

                if video_id in existing_video_ids:
                    self.stdout.write(
                        f"[KEEP] Active video HLS: {directory.name}"
                    )
                    continue

                if age_hours < older_than_hours:
                    self.stdout.write(
                        f"[KEEP] Recent orphan: {directory.name}"
                    )
                    continue

                candidates.append(
                    (directory, "orphan", video_id)
                )
                continue

            # Unknown directories are never deleted automatically.
            self.stdout.write(
                self.style.WARNING(
                    f"[KEEP] Unknown directory: {directory.name}"
                )
            )

        self.stdout.write(
            f"\nEligible directories: {len(candidates)}\n"
        )

        if not candidates:
            self.stdout.write(
                self.style.SUCCESS(
                    "Nothing needs to be cleaned up."
                )
            )
            return

        if not execute:
            for directory, reason, video_id in candidates:
                self.stdout.write(
                    self.style.WARNING(
                        f"[DRY RUN] Would remove: "
                        f"{directory.name} ({reason})"
                    )
                )

            self.stdout.write(
                "\nDry run completed. No files were deleted."
            )

            self.stdout.write(
                "Use --execute to perform the cleanup."
            )

            return

        deleted_count = 0
        skipped_count = 0

        self.stdout.write(
            "\nExecuting cleanup...\n"
        )

        for directory, reason, video_id in candidates:

            if not directory.exists():
                skipped_count += 1
                continue

            if directory.is_symlink():
                skipped_count += 1
                continue

            try:
                age_hours = self.get_age_hours(directory)

                if age_hours < older_than_hours:
                    skipped_count += 1
                    self.stdout.write(
                        f"[SKIP] Directory is no longer old enough: "
                        f"{directory.name}"
                    )
                    continue

                if reason == "orphan":
                    if Video.objects.filter(id=video_id).exists():
                        skipped_count += 1
                        self.stdout.write(
                            f"[SKIP] Video {video_id} now exists."
                        )
                        continue

                if reason == "backup":
                    output_dir = hls_root / str(video_id)

                    if not self.is_valid_hls_output(output_dir):
                        skipped_count += 1
                        self.stdout.write(
                            f"[SKIP] Main HLS output is not valid: "
                            f"{directory.name}"
                        )
                        continue

                shutil.rmtree(directory)

                deleted_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"[DELETED] {directory.name}"
                    )
                )

            except OSError as error:
                skipped_count += 1

                self.stdout.write(
                    self.style.ERROR(
                        f"[ERROR] Could not delete "
                        f"{directory.name}: {error}"
                    )
                )

        self.stdout.write(
            f"\nCleanup completed."
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted: {deleted_count}"
            )
        )

        if skipped_count:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped or failed: {skipped_count}"
                )
            )