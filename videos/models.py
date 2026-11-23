from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):

    name=models.CharField(
        max_length=100,
        unique=True
    )

    def __str__(self):
        return self.name

class Video(models.Model):

    user=models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    title=models.CharField(max_length=200)

    description=models.TextField()

    category=models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    video_file=models.FileField(
        upload_to="videos/"
    )

    thumbnail=models.ImageField(
        upload_to="thumbnails/",
        blank=True,
        null=True
    )

    views_count=models.PositiveIntegerField(
        default=0
    )

    duration = models.FloatField(default=0)

    created_at=models.DateTimeField(
        auto_now_add=True
    )

class VideoQuality(models.Model):

    QUALITY_CHOICES = [
        (480, "480p"),
        (720, "720p"),
        (1080, "1080p"),
    ]

    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="qualities",
    )

    resolution = models.PositiveIntegerField(
        choices=QUALITY_CHOICES,
    )

    video_file = models.FileField(
        upload_to="video_qualities/",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["video", "resolution"],
                name="unique_video_quality",
            ),
        ]
        ordering = ["resolution"]

    def __str__(self):
        return f"{self.video.title} - {self.resolution}p"

class VideoSubtitle(models.Model):

    LANGUAGE_CHOICES = [
        ("fa", "Persian"),
        ("en", "English"),
    ]

    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="subtitles",
    )

    language = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
    )

    label = models.CharField(
        max_length=50,
    )

    subtitle_file = models.FileField(
        upload_to="subtitles/",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["video", "language"],
                name="unique_subtitle_language_per_video",
            ),
        ]

    def __str__(self):
        return f"{self.video.title} - {self.label}"

class Subscription(models.Model):

    subscriber=models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subscriptions"
    )

    channel=models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subscribers"
    )

    created_at=models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        constraints=[
            models.UniqueConstraint(
                fields=["subscriber","channel"],
                name="unique_subscription"
            )
        ]

    def __str__(self):

        return (
            f"{self.subscriber.username} ->"
            f"{self.channel.username}"
        )

class VideoReaction(models.Model):

    LIKE="like"

    DISLIKE="dislike"

    REACTION_CHOICES=[
        (LIKE,"Like"),
        (DISLIKE,"Dislike")
    ]

    user=models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    video=models.ForeignKey(
        Video,
        on_delete=models.CASCADE
    )

    reaction_type=models.CharField(
        max_length=10,
        choices=REACTION_CHOICES
    )

    class Meta:

        constraints=[
            models.UniqueConstraint(
                fields=["user","video"],
                name="unique_user_video_reaction"
            )
        ]

class Comment(models.Model):

    user=models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    video=models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name="comments"
    )

    parent=models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies"
    )

    text=models.TextField()

    is_question = models.BooleanField(
        default=False
    )

    spoiler_ranges = models.JSONField(
        default=list,
        blank=True
    )

    is_removed = models.BooleanField(default=False)

    created_at=models.DateTimeField(
        auto_now_add=True
    )

class CommentLike(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="comment_likes"
    )

    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="likes"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "comment"],
                name="unique_user_comment_like"
            )
        ]

    def __str__(self):
        return f"{self.user.username} liked comment {self.comment_id}"

class CommentDislike(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="comment_dislikes"
    )

    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="dislikes"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "comment"],
                name="unique_user_comment_dislike"
            )
        ]

    def __str__(self):
        return f"{self.user.username} disliked comment {self.comment_id}"

class Notification(models.Model):

    class NotificationType(models.TextChoices):
        SUBSCRIPTION = "subscription", "Subscription"
        VIDEO_LIKE = "video_like", "Video Like"
        COMMENT = "comment", "Comment"
        COMMENT_REPLY = "comment_reply", "Comment Reply"
        COMMENT_LIKE = "comment_like", "Comment Like"
        ACTIVITY_DIGEST = "activity_digest", "Activity Digest"
        MILESTONE = "milestone", "Milestone"
        NEW_VIDEO = "new_video", "New Video"

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications"
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices
    )

    message = models.CharField(max_length=255)

    video = models.ForeignKey(
        Video,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications"
    )

    comment = models.ForeignKey(
        Comment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications"
    )

    interaction_count = models.PositiveIntegerField(
        default=0
    )

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.recipient.username} - "
            f"{self.notification_type}"
        )

class CommentReport(models.Model):

    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment or bullying"
        HATE_SPEECH = "hate_speech", "Hate speech"
        INAPPROPRIATE = "inappropriate", "Inappropriate content"
        MISINFORMATION = "misinformation", "Misleading information"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEWED = "reviewed", "Reviewed"
        DISMISSED = "dismissed", "Dismissed"
        ACTION_TAKEN = "action_taken", "Action taken"

    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="comment_reports"
    )

    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="reports"
    )

    reason = models.CharField(
        max_length=30,
        choices=Reason.choices
    )

    details = models.TextField(
        blank=True,
        max_length=500
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    created_at = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "comment"],
                name="unique_comment_report_per_user"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.reporter.username} reported "
            f"comment {self.comment_id}"
        )


class VideoReport(models.Model):

    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment or bullying"
        HATE_SPEECH = "hate_speech", "Hate speech"
        INAPPROPRIATE = "inappropriate", "Inappropriate content"
        MISINFORMATION = "misinformation", "Misleading information"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEWED = "reviewed", "Reviewed"
        DISMISSED = "dismissed", "Dismissed"
        ACTION_TAKEN = "action_taken", "Action taken"

    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="video_reports"
    )

    video = models.ForeignKey(
        Video,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports"
    )

    video_title = models.CharField(
        max_length=200,
        blank=True,
        default=""
    )

    video_owner = models.CharField(
        max_length=150,
        blank=True,
        default=""
    )

    reason = models.CharField(
        max_length=30,
        choices=Reason.choices
    )

    details = models.TextField(
        blank=True,
        max_length=500
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    created_at = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "video"],
                name="unique_video_report_per_user"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.reporter.username} reported "
            f"video {self.video_id}"
        )

class SubscriberMilestone(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subscriber_milestones"
    )
    milestone = models.PositiveIntegerField()
    reached_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "milestone"],
                name="unique_user_subscriber_milestone"
            )
        ]
        ordering = ["milestone"]

    def __str__(self):
        return f"{self.user.username} reached {self.milestone} subscribers"

class NotificationPreference(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="notification_preferences"
    )

    subscriptions_enabled = models.BooleanField(
        default=True
    )

    new_videos_enabled = models.BooleanField(
        default=True
    )

    video_likes_enabled = models.BooleanField(
        default=True
    )

    comments_enabled = models.BooleanField(
        default=True
    )

    comment_replies_enabled = models.BooleanField(
        default=True
    )

    comment_likes_enabled = models.BooleanField(
        default=True
    )

    milestones_enabled = models.BooleanField(
        default=True
    )

    activity_digest_enabled = models.BooleanField(
        default=False
    )

    comments_digest_threshold = models.PositiveIntegerField(
        default=100
    )

    pending_comment_interactions = models.PositiveIntegerField(
        default=0
    )

    def __str__(self):
        return f"Notification preferences: {self.user.username}"

class Profile(models.Model):

    user=models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    profile_image=models.ImageField(
        upload_to="profile_images/",
        blank=True,
        null=True
    )

    bio=models.TextField(
        max_length=500,
        blank=True
    )

    def __str__(self):
        return self.user.username

class VideoView(models.Model):

    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )


class LiveStream(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        LIVE = "live", "Live"
        ENDED = "ended", "Ended"
        FAILED = "failed", "Failed"

    class ArchiveStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="live_streams"
    )

    title = models.CharField(max_length=200)

    description = models.TextField(
        blank=True
    )

    thumbnail = models.ImageField(
        upload_to="live_thumbnails/",
        blank=True,
        null=True,
    )
    # SHA-256 hash of the private stream key.
    stream_key_hash = models.CharField(
        max_length=64,
        unique=True
    )

    # ID of the currently active MediaMTX publisher connection.
    active_source_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True
    )

    ended_at = models.DateTimeField(
        null=True,
        blank=True
    )

    archive_video = models.ForeignKey(
        Video,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="live_streams"
    )

    archive_status = models.CharField(
        max_length=10,
        choices=ArchiveStatus.choices,
        default=ArchiveStatus.PENDING,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="live_status_created_idx"
            ),
            models.Index(
                fields=["user", "status"],
                name="live_user_status_idx"
            ),
        ]

    def __str__(self):
        return f"{self.title} - {self.user.username}"


class LiveStreamReport(models.Model):

    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment or bullying"
        HATE_SPEECH = "hate_speech", "Hate speech"
        INAPPROPRIATE = "inappropriate", "Inappropriate content"
        MISINFORMATION = "misinformation", "Misleading information"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEWED = "reviewed", "Reviewed"
        DISMISSED = "dismissed", "Dismissed"
        ACTION_TAKEN = "action_taken", "Action taken"

    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="live_stream_reports"
    )

    live_stream = models.ForeignKey(
        LiveStream,
        on_delete=models.CASCADE,
        related_name="reports"
    )

    reason = models.CharField(
        max_length=30,
        choices=Reason.choices
    )

    details = models.TextField(
        blank=True,
        max_length=500
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    created_at = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "live_stream"],
                name="unique_live_stream_report_per_user"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.reporter.username} reported "
            f"live stream {self.live_stream_id}"
        )

class LiveChatMessage(models.Model):

    live_stream = models.ForeignKey(
        LiveStream,
        on_delete=models.CASCADE,
        related_name="chat_messages"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="live_chat_messages"
    )

    message = models.CharField(
        max_length=500
    )

    is_removed = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["live_stream", "created_at"],
                name="live_chat_stream_time_idx"
            ),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.message[:40]}"


class LiveChatMessageReport(models.Model):

    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment or bullying"
        HATE_SPEECH = "hate_speech", "Hate speech"
        INAPPROPRIATE = "inappropriate", "Inappropriate content"
        MISINFORMATION = "misinformation", "Misleading information"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEWED = "reviewed", "Reviewed"
        DISMISSED = "dismissed", "Dismissed"
        ACTION_TAKEN = "action_taken", "Action taken"

    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="live_chat_message_reports"
    )

    chat_message = models.ForeignKey(
        LiveChatMessage,
        on_delete=models.CASCADE,
        related_name="reports"
    )

    reason = models.CharField(
        max_length=30,
        choices=Reason.choices
    )

    details = models.TextField(
        blank=True,
        max_length=500
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    created_at = models.DateTimeField(auto_now_add=True)

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "chat_message"],
                name="unique_live_chat_report_per_user"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.reporter.username} reported "
            f"chat message {self.chat_message_id}"
        )

class LiveStreamReaction(models.Model):

    LIKE = "like"
    DISLIKE = "dislike"

    REACTION_CHOICES = [
        (LIKE, "Like"),
        (DISLIKE, "Dislike"),
    ]

    live_stream = models.ForeignKey(
        LiveStream,
        on_delete=models.CASCADE,
        related_name="reactions"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="live_stream_reactions"
    )

    reaction_type = models.CharField(
        max_length=10,
        choices=REACTION_CHOICES
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "live_stream"],
                name="unique_user_live_stream_reaction"
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.reaction_type} - Live {self.live_stream_id}"
