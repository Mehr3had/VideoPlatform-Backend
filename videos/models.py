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

    created_at=models.DateTimeField(
        auto_now_add=True
    )

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

