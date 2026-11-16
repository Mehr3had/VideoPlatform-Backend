import time
from pathlib import Path, PurePosixPath
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from videos.models import (
    Video,
    VideoQuality,
    VideoSubtitle,
    Profile,
)


class Command(BaseCommand):

    help = (
        "Find and safely remove old media files "
        "that are no longer referenced by database records."
    )

    MEDIA_FIELDS = [
        ("videos", Video, "video_file"),
        ("thumbnails", Video, "thumbnail"),
        ("video_qualities", VideoQuality, "video_file"),
        ("subtitles", VideoSubtitle, "subtitle_file"),
        ("profile_images", Profile, "profile_image"),
    ]

    def add_arguments(self, parser):

        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually delete eligible orphan files.",
        )

        parser.add_argument(
            "--older-than-hours",
            type=float,
            default=24,
            help="Only delete orphan files older than this many hours.",
        )

    @staticmethod
    def get_referenced_files(model, field_name):

        queryset = model.objects.exclude(
            **{f"{field_name}__isnull": True}
        ).exclude(
            **{field_name: ""}
        )

        return set(
            queryset.values_list(field_name, flat=True)
        )

    def get_all_referenced_files(self):

        referenced_files = set()

        for _, model, field_name in self.MEDIA_FIELDS:

            referenced_files.update(
                self.get_referenced_files(model, field_name)
            )

        return referenced_files

    @staticmethod
    def get_disk_files(directory, media_root):

        actual_files = set()
        resolved_directory = directory.resolve()

        for path in directory.rglob("*"):

            if path.is_symlink() or not path.is_file():
                continue

            try:
                path.resolve(strict=True).relative_to(
                    resolved_directory
                )

            except (OSError, ValueError):
                continue

            actual_files.add(
                path.relative_to(media_root).as_posix()
            )

        return actual_files

    @staticmethod
    def get_age_hours(path):

        age_seconds = time.time() - path.stat().st_mtime

        return age_seconds / 3600

    def handle(self, *args, **options):

        execute = options["execute"]
        older_than_hours = options["older_than_hours"]

        if older_than_hours <= 0:
            raise CommandError(
                "--older-than-hours must be greater than zero."
            )

        media_root = Path(settings.MEDIA_ROOT)

        if media_root.is_symlink() or not media_root.is_dir():
            raise CommandError(
                "MEDIA_ROOT must be an existing regular directory."
            )

        candidates = []

        self.stdout.write(
            f"\nMedia directory: {media_root}"
        )

        self.stdout.write(
            f"Age threshold: {older_than_hours} hours"
        )

        self.stdout.write(
            "\nScanning media files...\n"
        )

        total_orphans = 0
        total_missing = 0
        recent_orphans = 0

        # Inspect each known media directory.
        for folder, model, field_name in self.MEDIA_FIELDS:

            directory = media_root / folder

            self.stdout.write(
                f"\n{'=' * 45}"
            )

            self.stdout.write(
                f"Directory: {folder}"
            )

            if directory.is_symlink() or not directory.is_dir():

                self.stdout.write(
                    self.style.WARNING(
                        "Directory does not exist or is not a regular directory."
                    )
                )

                continue

            referenced_files = self.get_referenced_files(
                model,
                field_name,
            )

            actual_files = self.get_disk_files(
                directory,
                media_root,
            )

            orphan_files = sorted(
                actual_files - referenced_files
            )

            missing_files = sorted(
                referenced_files - actual_files
            )

            total_orphans += len(orphan_files)
            total_missing += len(missing_files)

            self.stdout.write(
                f"Files on disk: {len(actual_files)}"
            )

            self.stdout.write(
                f"Files referenced in DB: {len(referenced_files)}"
            )

            self.stdout.write(
                f"Orphan files: {len(orphan_files)}"
            )

            self.stdout.write(
                f"Missing files: {len(missing_files)}"
            )

            # Inspect orphan files.
            for relative_name in orphan_files:

                path = media_root / folder / Path(
                    *PurePosixPath(relative_name).parts[1:]
                )

                try:
                    age_hours = self.get_age_hours(path)
                    size_mb = path.stat().st_size / (1024 * 1024)

                except OSError:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[SKIP] Could not inspect: {relative_name}"
                        )
                    )
                    continue

                if age_hours < older_than_hours:

                    recent_orphans += 1

                    self.stdout.write(
                        f"[KEEP] Recent orphan: {relative_name} "
                        f"({age_hours:.1f}h)"
                    )

                    continue

                candidates.append(
                    (folder, relative_name)
                )

                status_label = (
                    "[DELETE]"
                    if execute
                    else "[DRY RUN]"
                )

                self.stdout.write(
                    f"{status_label} {relative_name} "
                    f"| {size_mb:.2f} MB "
                    f"| {age_hours:.1f}h"
                )

            # Report missing files.
            for relative_name in missing_files:

                self.stdout.write(
                    self.style.ERROR(
                        f"[MISSING] {relative_name}"
                    )
                )

        self.stdout.write(
            f"\n{'=' * 45}"
        )

        self.stdout.write(
            f"Total orphan files: {total_orphans}"
        )

        self.stdout.write(
            f"Recent files preserved: {recent_orphans}"
        )

        self.stdout.write(
            f"Missing referenced files: {total_missing}"
        )

        self.stdout.write(
            f"Eligible for deletion: {len(candidates)}"
        )

        if not candidates:

            self.stdout.write(
                self.style.SUCCESS(
                    "\nNothing needs to be cleaned up."
                )
            )

            return

        if not execute:

            self.stdout.write(
                self.style.WARNING(
                    "\nDry run completed. No files were deleted."
                )
            )

            self.stdout.write(
                "Use --execute to perform the cleanup."
            )

            return

        # Recheck references immediately before deletion.
        deleted_count = 0
        skipped_count = 0

        self.stdout.write(
            "\nExecuting media cleanup...\n"
        )

        for folder, relative_name in candidates:

            try:
                current_references = (
                    self.get_all_referenced_files()
                )

                if relative_name in current_references:

                    skipped_count += 1

                    self.stdout.write(
                        f"[SKIP] File is now referenced: {relative_name}"
                    )

                    continue

                path = (
                    media_root
                    / folder
                    / Path(
                        *PurePosixPath(relative_name).parts[1:]
                    )
                )

                allowed_directory = media_root / folder

                if (
                    path.is_symlink()
                    or not path.is_file()
                    or allowed_directory.is_symlink()
                    or not allowed_directory.is_dir()
                ):

                    skipped_count += 1

                    self.stdout.write(
                        f"[SKIP] File is no longer a regular file: "
                        f"{relative_name}"
                    )

                    continue

                try:
                    path.resolve(strict=True).relative_to(
                        allowed_directory.resolve()
                    )

                except (OSError, ValueError):

                    skipped_count += 1

                    self.stdout.write(
                        f"[SKIP] Unsafe file path: {relative_name}"
                    )

                    continue

                age_hours = self.get_age_hours(path)

                if age_hours < older_than_hours:

                    skipped_count += 1

                    self.stdout.write(
                        f"[SKIP] File is too recent: {relative_name}"
                    )

                    continue

                default_storage.delete(relative_name)

                if default_storage.exists(relative_name):

                    skipped_count += 1

                    self.stdout.write(
                        self.style.ERROR(
                            f"[ERROR] File still exists: {relative_name}"
                        )
                    )

                    continue

                deleted_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"[DELETED] {relative_name}"
                    )
                )

            except Exception as error:

                skipped_count += 1

                self.stdout.write(
                    self.style.ERROR(
                        f"[ERROR] {relative_name}: {error}"
                    )
                )

        self.stdout.write(
            "\nMedia cleanup completed."
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted files: {deleted_count}"
            )
        )

        if skipped_count:

            self.stdout.write(
                self.style.WARNING(
                    f"Skipped or failed: {skipped_count}"
                )
            )