import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.core.files.storage import default_storage
from django.db import transaction
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import Truncator

from .models import (
    Category,
    Content,
    Comment,
    CommentReport,
    LiveChatMessage,
    LiveChatMessageReport,
    LiveStream,
    LiveStreamReport,
    Profile,
    Video,
    VideoQuality,
    VideoReport,
    VideoSubtitle,
)

logger = logging.getLogger(__name__)


def delete_video_media_files(file_names, hls_dir):
    """Delete media files only after the database transaction commits."""

    for file_name in file_names:
        try:
            default_storage.delete(file_name)
        except Exception:
            logger.exception("Failed to delete video media file: %s", file_name)

    try:
        if hls_dir.exists():
            shutil.rmtree(str(hls_dir))
    except OSError:
        logger.exception("Failed to delete HLS directory: %s", hls_dir)




class SearchableListFilter(SimpleListFilter):
    template = "admin/videos/searchable_filter.html"


class ReporterFilter(SearchableListFilter):
    title = "Reporter"
    parameter_name = "reporter"

    def lookups(self, request, model_admin):
        rows = (
            model_admin.get_queryset(request)
            .order_by()
            .values_list("reporter_id", "reporter__username")
            .distinct()
            .order_by("reporter__username")
        )
        return [
            (str(user_id), username or f"User #{user_id}")
            for user_id, username in rows
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(reporter_id=self.value())
        return queryset


class DetailsProvidedFilter(SimpleListFilter):
    title = "Reporter details"
    parameter_name = "has_details"

    def lookups(self, request, model_admin):
        return (
            ("provided", "Details provided"),
            ("missing", "No details"),
        )

    def queryset(self, request, queryset):
        if self.value() == "provided":
            return queryset.exclude(details="")
        if self.value() == "missing":
            return queryset.filter(details="")
        return queryset


class VideoAvailabilityFilter(SimpleListFilter):
    title = "Video availability"
    parameter_name = "video_availability"

    def lookups(self, request, model_admin):
        return (
            ("available", "Video still exists"),
            ("deleted", "Video already deleted"),
        )

    def queryset(self, request, queryset):
        if self.value() == "available":
            return queryset.filter(video__isnull=False)
        if self.value() == "deleted":
            return queryset.filter(video__isnull=True)
        return queryset


class VideoOwnerFilter(SearchableListFilter):
    title = "Video owner"
    parameter_name = "video_owner_filter"

    def lookups(self, request, model_admin):
        owners = (
            model_admin.get_queryset(request)
            .exclude(video_owner="")
            .order_by()
            .values_list("video_owner", flat=True)
            .distinct()
            .order_by("video_owner")
        )
        return [(owner, owner) for owner in owners]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(video_owner=self.value())
        return queryset


class CommentAuthorFilter(SearchableListFilter):
    title = "Comment author"
    parameter_name = "comment_author"

    def lookups(self, request, model_admin):
        rows = (
            model_admin.get_queryset(request)
            .order_by()
            .values_list("comment__user_id", "comment__user__username")
            .distinct()
            .order_by("comment__user__username")
        )
        return [(str(user_id), username) for user_id, username in rows]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(comment__user_id=self.value())
        return queryset


class CommentVideoFilter(SearchableListFilter):
    title = "Related video"
    parameter_name = "comment_video"

    def lookups(self, request, model_admin):
        rows = (
            model_admin.get_queryset(request)
            .order_by()
            .values_list("comment__video_id", "comment__video__title")
            .distinct()
            .order_by("comment__video__title")
        )
        return [
            (str(video_id), title or f"Video #{video_id}")
            for video_id, title in rows
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(comment__video_id=self.value())
        return queryset


class CommentVisibilityFilter(SimpleListFilter):
    title = "Comment visibility"
    parameter_name = "comment_visibility"

    def lookups(self, request, model_admin):
        return (
            ("active", "Visible comments"),
            ("removed", "Removed comments"),
        )

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(comment__is_removed=False)
        if self.value() == "removed":
            return queryset.filter(comment__is_removed=True)
        return queryset


class ChatMessageAuthorFilter(SearchableListFilter):
    title = "Message author"
    parameter_name = "chat_message_author"

    def lookups(self, request, model_admin):
        rows = (
            model_admin.get_queryset(request)
            .order_by()
            .values_list(
                "chat_message__user_id",
                "chat_message__user__username",
            )
            .distinct()
            .order_by("chat_message__user__username")
        )
        return [(str(user_id), username) for user_id, username in rows]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(chat_message__user_id=self.value())
        return queryset


class ChatStreamFilter(SearchableListFilter):
    title = "Live stream"
    parameter_name = "chat_stream"

    def lookups(self, request, model_admin):
        rows = (
            model_admin.get_queryset(request)
            .order_by()
            .values_list(
                "chat_message__live_stream_id",
                "chat_message__live_stream__title",
            )
            .distinct()
            .order_by("chat_message__live_stream__title")
        )
        return [
            (str(stream_id), title or f"Stream #{stream_id}")
            for stream_id, title in rows
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                chat_message__live_stream_id=self.value()
            )
        return queryset


class ChatMessageVisibilityFilter(SimpleListFilter):
    title = "Message visibility"
    parameter_name = "message_visibility"

    def lookups(self, request, model_admin):
        return (
            ("active", "Visible messages"),
            ("removed", "Removed messages"),
        )

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(chat_message__is_removed=False)
        if self.value() == "removed":
            return queryset.filter(chat_message__is_removed=True)
        return queryset


class LiveChannelFilter(SearchableListFilter):
    title = "Channel owner"
    parameter_name = "stream_channel"

    def lookups(self, request, model_admin):
        rows = (
            model_admin.get_queryset(request)
            .order_by()
            .values_list(
                "live_stream__user_id",
                "live_stream__user__username",
            )
            .distinct()
            .order_by("live_stream__user__username")
        )
        return [(str(user_id), username) for user_id, username in rows]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(live_stream__user_id=self.value())
        return queryset


class LiveStreamStatusFilter(SimpleListFilter):
    title = "Broadcast status"
    parameter_name = "stream_status"

    def lookups(self, request, model_admin):
        return LiveStream.Status.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(live_stream__status=self.value())
        return queryset


class LiveArchiveStatusFilter(SimpleListFilter):
    title = "Archive status"
    parameter_name = "archive_status"

    def lookups(self, request, model_admin):
        return LiveStream.ArchiveStatus.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                live_stream__archive_status=self.value()
            )
        return queryset


class ReportAdminBase(admin.ModelAdmin):
    class Media:
        js = ('videos/admin/searchable_filter.js',)

    list_filter = (
        "status", "reason", ReporterFilter,
        DetailsProvidedFilter, "created_at",
    )
    list_editable = ("status",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    actions_on_top = True
    actions_on_bottom = False

    actions = (
        "mark_as_reviewed",
        "dismiss_reports",
    )

    confirm_template = "admin/videos/confirm_report_action.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Preserve moderation history.
        return False

    def save_model(self, request, obj, form, change):
        if change and "status" in form.changed_data:
            if obj.status == self.model.Status.PENDING:
                obj.reviewed_at = None
            else:
                obj.reviewed_at = timezone.now()

        super().save_model(request, obj, form, change)

    def _confirmation_response(
        self,
        request,
        queryset,
        title,
        message,
        content_count,
        content_label,
    ):
        select_across = request.POST.get("select_across") == "1"

        selected_ids = []
        if not select_across:
            selected_ids = list(
                queryset.values_list("pk", flat=True)
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": title,
            "message": message,
            "report_count": queryset.count(),
            "content_count": content_count,
            "content_label": content_label,
            "selected_ids": selected_ids,
            "select_across": select_across,
            "action_name": request.POST.get("action", ""),
            "index": request.POST.get("index", "0"),
            "form_action": request.get_full_path(),
            "cancel_url": request.get_full_path(),
        }

        return TemplateResponse(
            request,
            self.confirm_template,
            context,
        )

    @admin.action(description="Mark selected reports as reviewed")
    def mark_as_reviewed(self, request, queryset):
        now = timezone.now()

        count = queryset.update(
            status=self.model.Status.REVIEWED,
            reviewed_at=now,
        )

        self.message_user(
            request,
            f"{count} report(s) marked as reviewed.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Dismiss selected reports")
    def dismiss_reports(self, request, queryset):
        now = timezone.now()

        count = queryset.update(
            status=self.model.Status.DISMISSED,
            reviewed_at=now,
        )

        self.message_user(
            request,
            f"{count} report(s) dismissed.",
            level=messages.SUCCESS,
        )


@admin.register(VideoReport)
class VideoReportAdmin(ReportAdminBase):
    list_filter = ReportAdminBase.list_filter + (
        VideoAvailabilityFilter,
        VideoOwnerFilter,
    )

    list_display = (
        "id",
        "get_video_title",
        "video_owner",
        "reporter",
        "reason",
        "get_details_preview",
        "status",
        "created_at",
        "reviewed_at",
    )

    list_display_links = ("id", "get_video_title")

    search_fields = (
        "video_title",
        "video_owner",
        "video__title",
        "video__user__username",
        "reporter__username",
        "details",
    )

    fieldsets = (
        ("Reported Video", {
            "fields": ("video", "video_title", "video_owner")
        }),
        ("Report Information", {
            "fields": ("reporter", "reason", "details")
        }),
        ("Moderation", {
            "fields": ("status",)
        }),
        ("Review History", {
            "fields": ("created_at", "reviewed_at"),
            "classes": ("collapse",)
        }),
    )

    readonly_fields = (
        "video",
        "video_title",
        "video_owner",
        "reporter",
        "reason",
        "details",
        "created_at",
        "reviewed_at",
    )

    actions = ReportAdminBase.actions + (
        "delete_reported_videos",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "video",
            "video__user",
            "reporter",
        )

    @admin.display(description="Video")
    def get_video_title(self, obj):
        title = obj.video_title or "Untitled video"

        if obj.video_id:
            url = reverse(
                "admin:videos_content_change",
                args=(obj.video_id,),
            )
            return format_html('<a href="{}">{}</a>', url, title)

        return f"{title} (deleted)"

    @admin.display(description="Details")
    def get_details_preview(self, obj):
        return Truncator(obj.details).chars(75) if obj.details else "-"

    @admin.action(
        description="Delete reported videos and their media files"
    )
    def delete_reported_videos(self, request, queryset):
        if request.POST.get("_confirm_report_action") != "1":
            video_count = (
                queryset.exclude(video__isnull=True)
                .values("video_id")
                .distinct()
                .count()
            )

            return self._confirmation_response(
                request,
                queryset,
                "Confirm reported video deletion",
                (
                    "This permanently deletes the selected videos, "
                    "their uploaded files, thumbnails, quality files, "
                    "subtitles and generated HLS files. All reports "
                    "for these videos will be preserved and marked "
                    "as Action taken."
                ),
                video_count,
                "video(s)",
            )

        selected_report_ids = list(
            queryset.values_list("pk", flat=True)
        )

        video_ids = list(
            queryset.exclude(video__isnull=True)
            .values_list("video_id", flat=True)
            .distinct()
        )

        now = timezone.now()
        deleted_videos = 0
        updated_reports = 0

        with transaction.atomic():
            for video_id in video_ids:
                video = (
                    Video.objects.select_for_update()
                    .select_related("user")
                    .filter(pk=video_id)
                    .first()
                )

                if video is None:
                    continue

                video_title = video.title or ""
                video_owner = (
                    video.user.username if video.user_id else ""
                )

                file_names = []

                for field in (video.video_file, video.thumbnail):
                    if field and field.name:
                        file_names.append(field.name)

                for quality in video.qualities.all():
                    if quality.video_file and quality.video_file.name:
                        file_names.append(quality.video_file.name)

                for subtitle in video.subtitles.all():
                    if subtitle.subtitle_file and subtitle.subtitle_file.name:
                        file_names.append(subtitle.subtitle_file.name)

                file_names = list(dict.fromkeys(file_names))

                hls_dir = (
                    Path(settings.MEDIA_ROOT)
                    / "hls"
                    / str(video_id)
                )

                # Preserve every report before deleting the video.
                updated_reports += VideoReport.objects.filter(
                    video_id=video_id,
                ).update(
                    video=None,
                    video_title=video_title,
                    video_owner=video_owner,
                    status=VideoReport.Status.ACTION_TAKEN,
                    reviewed_at=now,
                )

                video.delete()

                transaction.on_commit(
                    lambda names=tuple(file_names), directory=hls_dir:
                        delete_video_media_files(names, directory)
                )

                deleted_videos += 1

            # Reports whose videos were already deleted are also resolved.
            updated_reports += VideoReport.objects.filter(
                pk__in=selected_report_ids,
                video__isnull=True,
            ).exclude(
                status=VideoReport.Status.ACTION_TAKEN,
            ).update(
                status=VideoReport.Status.ACTION_TAKEN,
                reviewed_at=now,
            )

        self.message_user(
            request,
            (
                f"{deleted_videos} video(s) deleted. "
                f"{updated_reports} report(s) preserved and marked "
                "as Action taken."
            ),
            level=messages.SUCCESS,
        )


@admin.register(CommentReport)
class CommentReportAdmin(ReportAdminBase):
    list_filter = ReportAdminBase.list_filter + (
        CommentAuthorFilter,
        CommentVideoFilter,
        CommentVisibilityFilter,
    )

    list_display = (
        "id",
        "get_comment_excerpt",
        "get_comment_author",
        "reporter",
        "reason",
        "get_details_preview",
        "status",
        "created_at",
        "reviewed_at",
    )

    list_display_links = ("id", "get_comment_excerpt")

    search_fields = (
        "comment__text",
        "comment__user__username",
        "comment__video__title",
        "reporter__username",
        "details",
    )

    fieldsets = (
        ("Reported Comment", {
            "fields": ("comment",)
        }),
        ("Report Information", {
            "fields": ("reporter", "reason", "details")
        }),
        ("Moderation", {
            "fields": ("status",)
        }),
        ("Review History", {
            "fields": ("created_at", "reviewed_at"),
            "classes": ("collapse",)
        }),
    )

    readonly_fields = (
        "comment",
        "reporter",
        "reason",
        "details",
        "created_at",
        "reviewed_at",
    )

    actions = ReportAdminBase.actions + (
        "remove_reported_comments",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "reporter",
            "comment",
            "comment__user",
            "comment__video",
        )

    @admin.display(description="Reported comment")
    def get_comment_excerpt(self, obj):
        if not obj.comment_id:
            return "Comment unavailable"

        return Truncator(obj.comment.text).chars(85)

    @admin.display(description="Comment author")
    def get_comment_author(self, obj):
        return obj.comment.user.username if obj.comment_id else "-"

    @admin.display(description="Details")
    def get_details_preview(self, obj):
        return Truncator(obj.details).chars(75) if obj.details else "-"

    @admin.action(
        description="Remove reported comments (preserve replies and reports)"
    )
    def remove_reported_comments(self, request, queryset):
        comment_ids = list(
            queryset.values_list("comment_id", flat=True).distinct()
        )

        if request.POST.get("_confirm_report_action") != "1":
            return self._confirmation_response(
                request,
                queryset,
                "Confirm comment removal",
                (
                    "Selected comments will be soft-removed. "
                    "Replies, comment records and all associated "
                    "reports will be preserved."
                ),
                len(comment_ids),
                "comment(s)",
            )

        now = timezone.now()

        with transaction.atomic():
            removed_count = Comment.objects.filter(
                pk__in=comment_ids,
                is_removed=False,
            ).update(is_removed=True)

            updated_reports = CommentReport.objects.filter(
                comment_id__in=comment_ids,
            ).update(
                status=CommentReport.Status.ACTION_TAKEN,
                reviewed_at=now,
            )

        self.message_user(
            request,
            (
                f"{removed_count} comment(s) soft-removed. "
                f"{updated_reports} associated report(s) marked "
                "as Action taken. Replies were preserved."
            ),
            level=messages.SUCCESS,
        )


@admin.register(LiveChatMessageReport)
class LiveChatMessageReportAdmin(ReportAdminBase):
    list_filter = ReportAdminBase.list_filter + (
        ChatMessageAuthorFilter,
        ChatStreamFilter,
        ChatMessageVisibilityFilter,
    )

    list_display = (
        "id",
        "get_message_excerpt",
        "get_message_author",
        "get_live_stream",
        "reporter",
        "reason",
        "get_details_preview",
        "status",
        "created_at",
        "reviewed_at",
    )

    list_display_links = ("id", "get_message_excerpt")

    search_fields = (
        "chat_message__message",
        "chat_message__user__username",
        "chat_message__live_stream__title",
        "reporter__username",
        "details",
    )

    fieldsets = (
        ("Reported Chat Message", {
            "fields": ("chat_message",)
        }),
        ("Report Information", {
            "fields": ("reporter", "reason", "details")
        }),
        ("Moderation", {
            "fields": ("status",)
        }),
        ("Review History", {
            "fields": ("created_at", "reviewed_at"),
            "classes": ("collapse",)
        }),
    )

    readonly_fields = (
        "chat_message",
        "reporter",
        "reason",
        "details",
        "created_at",
        "reviewed_at",
    )

    actions = ReportAdminBase.actions + (
        "remove_reported_messages",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "reporter",
            "chat_message",
            "chat_message__user",
            "chat_message__live_stream",
        )

    @admin.display(description="Reported message")
    def get_message_excerpt(self, obj):
        if not obj.chat_message_id:
            return "Message unavailable"

        return Truncator(obj.chat_message.message).chars(75)

    @admin.display(description="Message author")
    def get_message_author(self, obj):
        return obj.chat_message.user.username if obj.chat_message_id else "-"

    @admin.display(description="Live stream")
    def get_live_stream(self, obj):
        return (
            obj.chat_message.live_stream.title
            if obj.chat_message_id else "-"
        )

    @admin.display(description="Details")
    def get_details_preview(self, obj):
        return Truncator(obj.details).chars(75) if obj.details else "-"

    @admin.action(
        description="Remove reported chat messages (preserve reports)"
    )
    def remove_reported_messages(self, request, queryset):
        message_ids = list(
            queryset.values_list("chat_message_id", flat=True).distinct()
        )

        if request.POST.get("_confirm_report_action") != "1":
            return self._confirmation_response(
                request,
                queryset,
                "Confirm chat message removal",
                (
                    "Selected chat messages will be soft-removed. "
                    "The messages and their report history will remain "
                    "in the database."
                ),
                len(message_ids),
                "message(s)",
            )

        now = timezone.now()

        with transaction.atomic():
            removed_count = LiveChatMessage.objects.filter(
                pk__in=message_ids,
                is_removed=False,
            ).update(is_removed=True)

            updated_reports = LiveChatMessageReport.objects.filter(
                chat_message_id__in=message_ids,
            ).update(
                status=LiveChatMessageReport.Status.ACTION_TAKEN,
                reviewed_at=now,
            )

        self.message_user(
            request,
            (
                f"{removed_count} chat message(s) soft-removed. "
                f"{updated_reports} associated report(s) marked "
                "as Action taken."
            ),
            level=messages.SUCCESS,
        )


@admin.register(LiveStreamReport)
class LiveStreamReportAdmin(ReportAdminBase):
    list_filter = ReportAdminBase.list_filter + (
        LiveChannelFilter,
        LiveStreamStatusFilter,
        LiveArchiveStatusFilter,
    )

    list_display = (
        "id",
        "get_stream_title",
        "get_channel",
        "reporter",
        "reason",
        "get_details_preview",
        "status",
        "created_at",
        "reviewed_at",
    )

    list_display_links = ("id", "get_stream_title")

    search_fields = (
        "live_stream__title",
        "live_stream__user__username",
        "reporter__username",
        "details",
    )

    fieldsets = (
        ("Reported Live Stream", {
            "fields": ("live_stream",)
        }),
        ("Report Information", {
            "fields": ("reporter", "reason", "details")
        }),
        ("Moderation", {
            "fields": ("status",)
        }),
        ("Review History", {
            "fields": ("created_at", "reviewed_at"),
            "classes": ("collapse",)
        }),
    )

    readonly_fields = (
        "live_stream",
        "reporter",
        "reason",
        "details",
        "created_at",
        "reviewed_at",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "reporter",
            "live_stream",
            "live_stream__user",
        )

    @admin.display(description="Live stream")
    def get_stream_title(self, obj):
        if not obj.live_stream_id:
            return "Stream unavailable"

        url = reverse(
            "admin:videos_livestream_change",
            args=(obj.live_stream_id,),
        )

        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.live_stream.title,
        )

    @admin.display(description="Channel")
    def get_channel(self, obj):
        return (
            obj.live_stream.user.username
            if obj.live_stream_id else "-"
        )

    @admin.display(description="Details")
    def get_details_preview(self, obj):
        return Truncator(obj.details).chars(75) if obj.details else "-"


class VideoUploaderFilter(SearchableListFilter):
    title = "Uploaded by"
    parameter_name = "uploader"
    search_parameter = "uploader_search"
    template = "admin/videos/uploader_filter.html"

    minimum_query_length = 2
    result_limit = 20

    def __init__(self, request, params, model, model_admin):
        params.pop(self.search_parameter, None)
        super().__init__(request, params, model, model_admin)

    def has_output(self):
        return True

    def expected_parameters(self):
        return [self.parameter_name, self.search_parameter]

    def lookups(self, request, model_admin):
        from django.db.models import Q

        search_term = request.GET.get(
            self.search_parameter, ""
        ).strip()

        uploader_ids = (
            model_admin.get_queryset(request)
            .order_by()
            .values_list("user_id", flat=True)
            .distinct()
        )

        user_model = model_admin.model._meta.get_field(
            "user"
        ).remote_field.model

        base_users = user_model._default_manager.filter(
            pk__in=uploader_ids
        )

        selected_value = self.value()
        username_field = getattr(
            user_model, "USERNAME_FIELD", "username"
        )

        if len(search_term) < self.minimum_query_length:
            if not selected_value:
                return ()

            users = list(
                base_users.filter(pk=selected_value)[:1]
            )

        else:
            user_fields = {
                field.name: field
                for field in user_model._meta.concrete_fields
            }

            username_field = getattr(
                user_model, "USERNAME_FIELD", "username"
            )

            search_fields = []

            for field_name in dict.fromkeys((
                username_field,
                "username",
                "first_name",
                "last_name",
            )):
                field = user_fields.get(field_name)

                if field and field.get_internal_type() in {
                    "CharField",
                    "TextField",
                    "EmailField",
                }:
                    search_fields.append(field_name)

            if not search_fields:
                return ()

            combined_query = Q()

            for term in search_term.split():
                term_query = Q()

                for field_name in search_fields:
                    term_query |= Q(
                        **{f"{field_name}__icontains": term}
                    )

                combined_query &= term_query

            order_field = (
                username_field
                if username_field in user_fields
                else "pk"
            )

            users = list(
                base_users.filter(combined_query)
                .order_by(order_field, "pk")[:self.result_limit]
            )

            if selected_value and not any(
                str(user.pk) == selected_value
                for user in users
            ):
                selected_user = base_users.filter(
                    pk=selected_value
                ).first()

                if selected_user:
                    users.insert(0, selected_user)
                    users = users[:self.result_limit]

        choices = []

        for user in users:
            get_username = getattr(user, "get_username", None)

            username = (
                get_username()
                if callable(get_username)
                else str(getattr(user, username_field, user.pk))
            )

            get_full_name = getattr(user, "get_full_name", None)

            full_name = (
                get_full_name()
                if callable(get_full_name)
                else ""
            )

            label = (
                f"{full_name} (@{username})"
                if full_name
                else username
            )

            choices.append((str(user.pk), label))

        return choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(user_id=self.value())

        return queryset


@admin.register(Content)
class VideoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "user",
        "category",
        "views_count",
        "duration",
        "created_at",
    )

    list_filter = ('category', 'created_at', VideoUploaderFilter)
    search_fields = ("title", "user__username", "description")
    fieldsets = (
        ("Video Information", {
            "fields": ("user", "title", "description", "category")
        }),
        ("Media Files", {
            "fields": ("video_file", "thumbnail")
        }),
        ("Statistics", {
            "fields": ("views_count", "duration")
        }),
        ("Publication", {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("created_at",)
    list_select_related = ("user", "category")

    # Use the report moderation action for safe media deletion.
    class Media:
        js = ("videos/admin/searchable_filter.js",)


    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "video",
        "text",
        "is_removed",
        "is_question",
        "created_at",
    )

    list_filter = ("is_removed", "is_question", "created_at")
    search_fields = ("text", "user__username", "video__title")
    readonly_fields = ("created_at",)
    list_select_related = ("user", "video")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LiveStream)
class LiveStreamAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "user",
        "status",
        "archive_status",
        "started_at",
        "ended_at",
    )

    list_filter = ("status", "archive_status", "created_at")
    search_fields = ("title", "user__username")
    list_select_related = ("user",)

    # Never expose private publisher credentials or manually alter live state.
    exclude = ("stream_key_hash", "active_source_id")

    readonly_fields = (
        "status",
        "started_at",
        "ended_at",
        "archive_video",
        "archive_status",
        "created_at",
        "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LiveChatMessage)
class LiveChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "live_stream",
        "user",
        "message",
        "is_removed",
        "created_at",
    )

    list_filter = ("is_removed", "created_at")
    search_fields = (
        "message",
        "user__username",
        "live_stream__title",
    )

    list_select_related = ("live_stream", "user")
    readonly_fields = ("created_at",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VideoSubtitle)
class VideoSubtitleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "video",
        "language",
        "label",
        "created_at",
    )

    list_filter = ("language", "created_at")
    search_fields = ("video__title", "label")
    list_select_related = ("video",)


@admin.register(VideoQuality)
class VideoQualityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "video",
        "resolution",
        "created_at",
    )

    list_filter = ("resolution", "created_at")
    search_fields = ("video__title",)
    list_select_related = ("video",)


admin.site.register(Category)
admin.site.register(Profile)

admin.site.site_header = "Video Platform Administration"
admin.site.site_title = "Video Platform Admin"
admin.site.index_title = "Platform Management"