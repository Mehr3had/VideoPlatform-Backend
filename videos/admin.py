from django.contrib import admin
from .models import Video, Comment, Category, Profile, CommentReport
from django.utils import timezone

admin.site.register(Video)
admin.site.register(Comment)
admin.site.register(Category)
admin.site.register(Profile)

@admin.register(CommentReport)
class CommentReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "get_comment_author",
        "reporter",
        "reason",
        "details",
        "status",
        "created_at",
        "reviewed_at",
    )

    list_filter = ("status", "reason", "created_at")

    actions = ["delete_reported_comments"]

    search_fields = (
        "comment__text",
        "comment__user__username",
        "reporter__username",
        "details",
    )

    fields = (
        "comment",
        "reporter",
        "reason",
        "details",
        "status",
        "created_at",
        "reviewed_at",
    )

    list_editable = ("status",)

    readonly_fields = ("created_at", "reviewed_at")

    ordering = ("-created_at",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related(
            "reporter",
            "comment",
            "comment__user",
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        extra_context["pending_reports_count"] = (
            CommentReport.objects.filter(
                status=CommentReport.Status.PENDING
            ).count()
        )

        return super().changelist_view(
            request,
            extra_context=extra_context,
        )

    def save_model(self, request, obj, form, change):
        if change and "status" in form.changed_data:
            if obj.status in [
                CommentReport.Status.REVIEWED,
                CommentReport.Status.DISMISSED,
                CommentReport.Status.ACTION_TAKEN,
            ]:
                if obj.reviewed_at is None:
                    obj.reviewed_at = timezone.now()
            else:
                obj.reviewed_at = None

        super().save_model(request, obj, form, change)

    @admin.display(description="Comment Author")
    def get_comment_author(self, obj):
        return obj.comment.user.username

    @admin.action(description="Remove reported comments (keep replies)")
    def delete_reported_comments(self, request, queryset):
        comment_ids = queryset.values_list("comment_id", flat=True).distinct()
        comments = Comment.objects.filter(
            id__in=comment_ids,
            is_removed=False,
        )

        count = comments.update(
            text="این کامنت به‌دلیل نقض مقررات حذف شد.",
            is_removed=True,
        )

        self.message_user(
            request,
            f"{count} comment(s) marked as removed. Replies and reports were preserved."
        )
