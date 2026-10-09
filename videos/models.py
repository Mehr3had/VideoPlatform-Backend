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
    text=models.TextField()

    created_at=models.DateTimeField(
        auto_now_add=True
    )

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

