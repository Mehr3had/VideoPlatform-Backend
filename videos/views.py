from django.shortcuts import render,get_object_or_404,redirect # type: ignore
from .models import CommentDislike, CommentReport, Video,VideoReaction,Category,Subscription,Profile,VideoView
from .models import Comment, CommentLike, Notification, NotificationPreference,SubscriberMilestone,LiveStream,LiveChatMessage,LiveStreamReaction,LiveStreamReport,LiveChatMessageReport
from django.contrib.auth.decorators import login_required # type: ignore
from django.contrib.auth.models import User # type: ignore
from rest_framework.response import Response # type: ignore
from rest_framework import status # type: ignore
from django.contrib.auth import authenticate,login as auth_login # type: ignore
from django.contrib.auth import logout
from django.middleware.csrf import get_token
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.tokens import RefreshToken # type: ignore
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken # type: ignore
from rest_framework.permissions import IsAuthenticated,IsAdminUser,AllowAny # type: ignore
from rest_framework.decorators import api_view,permission_classes # type: ignore
from django.db.models import Q # type: ignore
from django.core.paginator import Paginator # type: ignore
from django.utils import timezone # type: ignore
from datetime import timedelta
from rest_framework.pagination import PageNumberPagination # type: ignore
from rest_framework_simplejwt.serializers import TokenRefreshSerializer # type: ignore
from django.db.models import F # type: ignore
from django.core.mail import send_mail # type: ignore
from django.conf import settings  # type: ignore
from django.contrib.auth.tokens import default_token_generator # type: ignore
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode # type: ignore
from django.utils.encoding import force_bytes # type: ignore
from django.utils.dateparse import parse_datetime
from django.db import transaction # type: ignore
from django.core.files.storage import default_storage
from .translations import MESSAGES, get_messages
from .services.hls import generate_hls, HLSGenerationError
import os
import logging
import subprocess
import shutil
import hashlib
import secrets
import re
from PIL import Image
from django.core.files import File

logger = logging.getLogger(__name__)

class VideoPagination(PageNumberPagination):
    page_size = 6
    page_size_query_param = "page_size"
    max_page_size = 20

def notify_subscribers_new_video(video):
    subscribers = Subscription.objects.filter(
        channel=video.user
    ).select_related("subscriber")

    for subscription in subscribers:
        subscriber = subscription.subscriber

        preferences, _ = NotificationPreference.objects.get_or_create(
            user=subscriber
        )

        if not preferences.new_videos_enabled:
            continue

        message = (
            f'{video.user.username} uploaded a new video: {video.title}'
        )

        Notification.objects.create(
            recipient=subscriber,
            sender=video.user,
            notification_type=Notification.NotificationType.NEW_VIDEO,
            message=message,
            video=video
        )

def notify_comment_interaction(
    recipient,
    sender,
    video,
    comment,
    message,
    notification_type
):
    preferences, _ = NotificationPreference.objects.get_or_create(
        user=recipient
    )

    # Respect the user's comment/reply notification preferences.
    if notification_type == Notification.NotificationType.COMMENT_REPLY:
        if not preferences.comment_replies_enabled:
            return

    elif notification_type == Notification.NotificationType.COMMENT:
        if not preferences.comments_enabled:
            return

     # If digest mode is disabled, send an individual notification.
    if not preferences.activity_digest_enabled:
        Notification.objects.create(
            recipient=recipient,
            sender=sender,
            notification_type=notification_type,
            message=message,
            video=video,
            comment=comment
        )
        return

     # Digest mode: count eligible comment interactions.
    preferences.pending_comment_interactions += 1

    threshold = max(1, preferences.comments_digest_threshold)

    if preferences.pending_comment_interactions >= threshold:
        interaction_count = preferences.pending_comment_interactions

        Notification.objects.create(
            recipient=recipient,
            sender=None,
            notification_type=Notification.NotificationType.ACTIVITY_DIGEST,
            message=f"You received {interaction_count} new comment interactions.",
            video=video,
            interaction_count=interaction_count
        )

        preferences.pending_comment_interactions = 0

    preferences.save(
        update_fields=["pending_comment_interactions"]
    )

def validate_video_file(video_file):

    if not video_file:

        return "Video file is required."

    video_extension=os.path.splitext(
        video_file.name
    )[1].lower()

    allowed_extensions=[
        ".mp4",
        ".webm"
    ]

    if video_extension not in allowed_extensions:

        return "Only MP4 and WebM videos are allowed."

    max_size =100 * 1024 * 1024

    if video_file.size>max_size:

        return "Video file must be smaller than 100 MB."

    return None

def validate_thumbnail_file(thumbnail):

    if not thumbnail:

        return None

    thumbnail_extension = os.path.splitext(
        thumbnail.name
    )[1].lower()

    allowed_extensions=[
        ".jpg",
        ".jpeg",
        ".png",
        ".webp"
    ]

    if thumbnail_extension not in allowed_extensions:
        return "Only image files are allowed for thumbnail."

    max_size =5 * 1024 * 1024

    if thumbnail.size>max_size:
        return "Thumbnail must be smaller than 5 MB."

    return None

def validate_live_thumbnail_file(thumbnail):
    if not thumbnail:
        return None

    allowed_formats = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
    }

    extension = os.path.splitext(thumbnail.name)[1].lower()

    if extension not in allowed_formats:
        return "Only JPG, PNG, and WebP images are allowed."

    max_size = 5 * 1024 * 1024

    if thumbnail.size > max_size:
        return "Thumbnail must be smaller than 5 MB."

    try:
        thumbnail.seek(0)

        with Image.open(thumbnail) as image:
            actual_format = image.format
            width, height = image.size

            if actual_format != allowed_formats[extension]:
                return "Image content does not match its file extension."

            if (
                width > 8192
                or height > 8192
                or width * height > 40_000_000
            ):
                return "Thumbnail dimensions are too large."

            image.verify()

        thumbnail.seek(0)

    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        thumbnail.seek(0)
        return "The selected thumbnail is not a valid image."

    return None

def video_detail(request,video_id):

    video=get_object_or_404(
        Video,
        id=video_id
    )

    viewed_videos=request.session.get(
        "viewed_videos",
        []
    )

    if video.id not in viewed_videos:

        video.views_count+=1

        video.save(
            update_fields=["views_count"]
        )

        viewed_videos.append(video.id)

        request.session["viewed_videos"]=viewed_videos

    likes_count=VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.LIKE
    ).count()

    dislikes_count=VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.DISLIKE
    ).count()

    comments=Comment.objects.filter(
        video=video
    ).order_by("-created_at")

    return render(
        request,
        "videos/video_detail.html",
        {
            "video":video,
            "likes_count":likes_count,
            "dislikes_count":dislikes_count,
            "comments":comments
        }
    )

@api_view(["GET"])
def video_detail_api(request, video_id):

    video = get_object_or_404(
        Video,
        id=video_id
    )

    likes_count = VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.LIKE
    ).count()

    dislikes_count = VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.DISLIKE
    ).count()

    subtitles = [
        {
            "language": subtitle.language,
            "label": subtitle.label,
            "src": request.build_absolute_uri(
                subtitle.subtitle_file.url
            ),
        }
        for subtitle in video.subtitles.all()
    ]

    qualities = [
        {
            "resolution": quality.resolution,
            "label": f"{quality.resolution}p",
            "src": request.build_absolute_uri(
                quality.video_file.url
            ),
        }
        for quality in video.qualities.all()
    ]

    hls_playlist_path = (
        settings.MEDIA_ROOT / "hls" / str(video.id) / "index.m3u8"
    )

    if hls_playlist_path.is_file():
        hls_version = hls_playlist_path.stat().st_mtime_ns

        hls_url = request.build_absolute_uri(
            f"{settings.MEDIA_URL}hls/{video.id}/index.m3u8?v={hls_version}"
        )
    else:
        hls_url = None

    response = Response({
        "id": video.id,
        "title": video.title,
        "description": video.description,
        "thumbnail": (
            request.build_absolute_uri(
                video.thumbnail.url
            )
            if video.thumbnail
            else None
        ),
        "video_file": request.build_absolute_uri(
            video.video_file.url
        ),
        "hls_url": hls_url,
        "qualities": qualities,
        "subtitles": subtitles,
        "category_id": (
            video.category.id
            if video.category
            else None
        ),
        "views_count": video.views_count,
        "username": video.user.username,
        "user_id": video.user.id,
        "created_at": video.created_at,
        "likes_count": likes_count,
        "dislikes_count": dislikes_count,
    })

    response["Cache-Control"] = "no-store"
    return response

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def react_to_video(request, video_id):
    video = get_object_or_404(Video, id=video_id)

    if request.method == "GET":
        reaction = VideoReaction.objects.filter(
            user=request.user,
            video=video
        ).first()

        likes_count = VideoReaction.objects.filter(
            video=video,
            reaction_type=VideoReaction.LIKE
        ).count()

        dislikes_count = VideoReaction.objects.filter(
            video=video,
            reaction_type=VideoReaction.DISLIKE
        ).count()

        return Response({
            "reaction": reaction.reaction_type if reaction else None,
            "likes_count": likes_count,
            "dislikes_count": dislikes_count,
        })

    reaction_type = request.data.get(
        "reaction", ""
    ).lower().strip()

    if reaction_type not in [
        VideoReaction.LIKE,
        VideoReaction.DISLIKE
    ]:
        return Response(
            {"error": "Invalid reaction"},
            status=status.HTTP_400_BAD_REQUEST
        )

    reaction, created = VideoReaction.objects.get_or_create(
        user=request.user,
        video=video,
        defaults={"reaction_type": reaction_type}
    )

    # Existing reaction: prevent duplicate likes and dislikes.
    if not created:
        if reaction.reaction_type == reaction_type:
            message = f"You already {reaction_type}d this video"
        else:
            reaction.reaction_type = reaction_type
            reaction.save(update_fields=["reaction_type"])
            message = "Reaction updated successfully"

    else:
        message = "Reaction saved successfully"

    # Create or update an aggregated notification only for a new LIKE.
    if (
        reaction_type == VideoReaction.LIKE
        and created
        and video.user_id != request.user.id
    ):
        preferences, _ = NotificationPreference.objects.get_or_create(
            user=video.user
        )

        if preferences.video_likes_enabled:
            notification = Notification.objects.filter(
                recipient=video.user,
                notification_type=Notification.NotificationType.VIDEO_LIKE,
                video=video,
                is_read=False
            ).first()

            if notification:
                Notification.objects.filter(
                    id=notification.id
                ).update(
                    interaction_count=F("interaction_count") + 1,
                    sender=request.user,
                    message="Someone liked your video."
                )
            else:
                Notification.objects.create(
                    recipient=video.user,
                    sender=request.user,
                    notification_type=Notification.NotificationType.VIDEO_LIKE,
                    message="Someone liked your video.",
                    video=video,
                    interaction_count=1
                )

    likes_count = VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.LIKE
    ).count()

    dislikes_count = VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.DISLIKE
    ).count()

    return Response({
        "message": message,
        "reaction": reaction.reaction_type,
        "likes_count": likes_count,
        "dislikes_count": dislikes_count
    })

@api_view(["POST"])
def register_api(request):
    username = request.data.get("username", "").strip()
    email = request.data.get("email", "").strip().lower()
    password = request.data.get("password", "")
    password_confirm = request.data.get("password_confirm", "")
    messages = get_messages(request)

    if not username or not email or not password or not password_confirm:
        return Response(
            {"error": messages["all_fields_required."]},
            status=status.HTTP_400_BAD_REQUEST
        )

    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError

    try:
        validate_email(email)
    except ValidationError:
        return Response(
            {"error": messages["invalid_email"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(email__iexact=email).exists():
        return Response(
            {"error": messages["email_exists"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if password != password_confirm:
        return Response(
            {"error": messages["password_mismatch"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(password) < 8:
        return Response(
            {"error": messages["password_too_short"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": messages["username_exists"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )

    return Response(
        {
            "message": messages["registration_success"],
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        status=status.HTTP_201_CREATED
    )

@api_view(["POST"])
def forgot_username_api(request):

    email = request.data.get("email", "").strip().lower()

    if not email:
        return Response(
            {"error": "Email is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    users = User.objects.filter(email__iexact=email)

    if users.exists():

        usernames = list(
            users.values_list("username", flat=True)
        )

        message = (
            "Hello,\n\n"
            "The username(s) associated with your email address are:\n\n"
            + "\n".join(usernames)
            + "\n\nIf you did not request this, you can ignore this email."
        )

        send_mail(
            subject="VideoPlatform - Username Recovery",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

    return Response(
        {
            "message": (
                "If an account is associated with this email, "
                "you will receive an email with further instructions."
            )
        },
        status=status.HTTP_200_OK
    )

@api_view(["POST"])
def password_reset_request_api(request):
    messages = get_messages(request)
    print("TRANSLATED MESSAGE:", messages["password_reset_email_message"])
    email = request.data.get("email", "").strip().lower()

    if not email:
        return Response(
            {"error": messages["email_required"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    users = User.objects.filter(email__iexact=email)

    for user in users:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        reset_link = (
            f"http://localhost:3000/reset-password/"
            f"?uid={uid}&token={token}"
        )

        message = (
            f"{messages['password_reset_email_greeting'].format(username=user.username)}\n\n"
            f"{messages['password_reset_email_intro']}\n\n"
            f"{messages['password_reset_email_instruction']}\n"
            f"{reset_link}\n\n"
            f"{messages['password_reset_email_ignore']}"
        )

        print("DEBUG RESET LINK:", reset_link)

        send_mail(
            subject=messages["password_reset_email_subject"],
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

    return Response(
        {"message": messages["password_reset_email_message"]},
        status=status.HTTP_200_OK
    )

@api_view(["POST"])
def password_reset_confirm_api(request):
    messages = get_messages(request)
    uid = request.data.get("uid", "")
    token = request.data.get("token", "")
    new_password = request.data.get("new_password", "")
    password_confirm = request.data.get("password_confirm", "")

    if not all([uid, token, new_password, password_confirm]):
        return Response(
            {"error": messages["all_fields_required"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if new_password != password_confirm:
        return Response(
            {"error": messages["passwords_mismatch"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(new_password) < 8:
        return Response(
            {"error": messages["password_too_short"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user_id = urlsafe_base64_decode(uid).decode()
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response(
            {"error": messages["invalid_reset_link"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not default_token_generator.check_token(user, token):
        return Response(
            {"error": messages["invalid_reset_link"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    return Response(
        {"message": messages["password_reset_success"]},
        status=status.HTTP_200_OK
    )

@api_view(["GET"])
@permission_classes([AllowAny])
def csrf_token_api(request):
    csrf_token = get_token(request._request)

    return Response(
        {"csrfToken": csrf_token},
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@permission_classes([AllowAny])
def login_api(request):
    messages = get_messages(request)
    username = request.data.get("username", "").strip()
    password = request.data.get("password", "")
    SessionAuthentication().enforce_csrf(request)

    if not username or not password:
        return Response(
            {"error": messages["credentials_required"]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(
        request,
        username=username,
        password=password,
    )

    if user is None:
        return Response(
            {"error": messages["invalid_credentials"]},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    refresh = RefreshToken.for_user(user)

    response = Response(
        {
            "message": messages["login_success"],
            "username": user.username,
            "access": str(refresh.access_token),
        },
        status=status.HTTP_200_OK,
    )

    response.set_cookie(
        key="refresh_token",
        value=str(refresh),
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        path="/videos/",
    )

    return response

@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_token_api(request):
    SessionAuthentication().enforce_csrf(request)
    refresh_token = request.COOKIES.get("refresh_token")

    if not refresh_token:
        return Response(
            {"error": "Refresh token is missing."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    serializer = TokenRefreshSerializer(
        data={"refresh": refresh_token}
    )

    try:
        is_valid = serializer.is_valid()
    except (TokenError, InvalidToken):
        is_valid = False

    if not is_valid:
        response = Response(
            {"error": "Session expired. Please log in again."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
        response.delete_cookie("refresh_token", path="/videos/")
        return response

    data = serializer.validated_data
    access_token = data["access"]

    response = Response(
        {"access": access_token},
        status=status.HTTP_200_OK,
    )

    # Replace the cookie when refresh-token rotation is enabled.
    if "refresh" in data:
        response.set_cookie(
            key="refresh_token",
            value=data["refresh"],
            max_age=7 * 24 * 60 * 60,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Lax",
            path="/videos/",
        )

    return response

@api_view(["POST"])
@permission_classes([AllowAny])
def logout_api(request):
    SessionAuthentication().enforce_csrf(request)
    refresh_token = request.COOKIES.get("refresh_token")

    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except (TokenError, InvalidToken):
            pass

    response = Response(
        {"message": "Logged out successfully."},
        status=status.HTTP_200_OK,
    )

    response.delete_cookie(
        key="refresh_token",
        path="/videos/",
    )

    return response

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    return Response({
        "id": request.user.id,
        "username": request.user.username,
        "is_admin": request.user.is_staff,
    })

@api_view(["GET"])
def user_profile_api(request, user_id):

    user = get_object_or_404(
        User,
        id=user_id
    )

    profile = getattr(
        user,
        "profile",
        None
    )

    subscribers_count = Subscription.objects.filter(
        channel=user
    ).count()

    videos_count = Video.objects.filter(
        user=user
    ).count()

    is_subscribed = False

    if request.user.is_authenticated:

        is_subscribed = Subscription.objects.filter(
            subscriber=request.user,
            channel=user
        ).exists()

    is_owner = (
        request.user.is_authenticated
        and request.user.id == user.id
    )

    return Response({
        "id": user.id,
        "username": user.username,
        "bio": profile.bio if profile else "",
        "profile_image": (
            request.build_absolute_uri(
                profile.profile_image.url
            )
            if profile and profile.profile_image
            else None
        ),
        "videos_count": videos_count,
        "subscribers_count": subscribers_count,
        "is_subscribed": is_subscribed,
        "is_owner": is_owner,
    })

@api_view(["GET"])
def user_videos_api(request, user_id):

    user = get_object_or_404(
        User,
        id=user_id
    )

    videos = Video.objects.filter(
        user=user
    ).order_by("-created_at")

    data = []

    for video in videos:

        data.append({
            "id": video.id,
            "title": video.title,
            "description": video.description,
            "thumbnail": (
                request.build_absolute_uri(
                    video.thumbnail.url
                )
                if video.thumbnail
                else None
            ),
            "video_file": request.build_absolute_uri(
                video.video_file.url
            ),
            "views_count": video.views_count,
            "username": video.user.username,
            "created_at": video.created_at,
        })

    return Response(data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_subscription_api(request, user_id):
    messages = get_messages(request)
    channel = get_object_or_404(
        User,
        id=user_id
    )

    if request.user == channel:

        return Response(
            {"error": messages["subscribe_self"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    subscription = Subscription.objects.filter(
        subscriber=request.user,
        channel=channel
    ).first()

    if subscription:

        subscription.delete()
        subscribed = False

    else:

        Subscription.objects.create(
            subscriber=request.user,
            channel=channel
        )

        subscribed = True
        notify_subscriber_milestone(channel)

    subscribers_count = Subscription.objects.filter(
        channel=channel
    ).count()

    return Response({
        "subscribed": subscribed,
        "subscribers_count": subscribers_count,
    })

@api_view(["GET"])
def video_list_api(request):
    search = request.GET.get("search", "").strip()
    category_id = request.GET.get("category")

    videos = Video.objects.all().order_by("-created_at")

    if search:
        videos = videos.filter(title__icontains=search)

    if category_id:
        videos = videos.filter(category_id=category_id)

    paginator = VideoPagination()

    page = paginator.paginate_queryset(videos, request)

    data = []

    for video in page:
        data.append({
            "id": video.id,
            "title": video.title,
            "description": video.description,
            "thumbnail": (
                request.build_absolute_uri(video.thumbnail.url)
                if video.thumbnail else None
            ),
            "video_file": request.build_absolute_uri(video.video_file.url),
            "views_count": video.views_count,
            "username": video.user.username,
            "duration": video.duration,
            "created_at": video.created_at,
            "category_id": video.category.id if video.category else None,
            "category_name": video.category.name if video.category else None,
        })

    return paginator.get_paginated_response(data)

@api_view(["GET"])
def trending_videos_api(request):
    videos = Video.objects.all().order_by("-views_count", "-created_at")[:6]

    data = []

    for video in videos:
        data.append({
            "id": video.id,
            "title": video.title,
            "thumbnail": (
                request.build_absolute_uri(video.thumbnail.url)
                if video.thumbnail else None
            ),
            "views_count": video.views_count,
            "username": video.user.username,
            "duration": video.duration,
            "created_at": video.created_at,
        })

    return Response(data)

@api_view(["GET"])
def tail_api(request, video_id):

    video = get_object_or_404(
        Video,
        id=video_id
    )

    likes_count = VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.LIKE
    ).count()

    dislikes_count = VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.DISLIKE
    ).count()

    data = {
        "id": video.id,
        "title": video.title,
        "description": video.description,
        "thumbnail": request.build_absolute_uri(
            video.thumbnail.url
        ) if video.thumbnail else None,
        "video_file": request.build_absolute_uri(
            video.video_file.url
        ),
        "views_count": video.views_count,
        "likes_count": likes_count,
        "dislikes_count": dislikes_count,
        "username": video.user.username,
        "created_at": video.created_at,
    }

    return Response(data)

@api_view(["POST"])
def increment_view_count(request, video_id):

    video = get_object_or_404(
        Video,
        id=video_id
    )

    now = timezone.now()
    thirty_minutes_ago = now - timedelta(minutes=30)

    user = request.user if request.user.is_authenticated else None

    ip_address = request.META.get(
        "REMOTE_ADDR"
    )

    if user:

        recent_view = VideoView.objects.filter(
            video=video,
            user=user,
            created_at__gte=thirty_minutes_ago
        ).exists()

    else:

        recent_view = VideoView.objects.filter(
            video=video,
            user__isnull=True,
            ip_address=ip_address,
            created_at__gte=thirty_minutes_ago
        ).exists()

    if recent_view:

        return Response({
            "message": "View already counted recently.",
            "views_count": video.views_count,
            "counted": False
        })

    VideoView.objects.create(
        video=video,
        user=user,
        ip_address=ip_address
    )

    video.views_count += 1

    video.save(
        update_fields=["views_count"]
    )

    return Response({
        "message": "View counted successfully.",
        "views_count": video.views_count,
        "counted": True
    })

@login_required
def logout_view(request):

    if request.method=="POST":

        logout(request)

        return redirect("home")

    return redirect("home")

def home(request):

    query = request.GET.get("q")

    category_id = request.GET.get("category")

    video_list = Video.objects.all()

    if query:

        video_list = video_list.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query)
        )

    if category_id:

        video_list = video_list.filter(
            category_id=category_id
        )

    video_list = video_list.order_by("-created_at")

    paginator = Paginator(video_list, 6)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    categories = Category.objects.all().order_by("name")

    trending_videos = Video.objects.order_by("-views_count")[:4]

    return render(
        request,
        "videos/home.html",
        {
            "video_list": video_list,
            "page_obj": page_obj,
            "trending_videos": trending_videos,
            "query": query,
            "categories": categories,
            "selected_category": category_id
        }
    )

def validate_spoiler_ranges(ranges, text):
    if not isinstance(ranges, list):
        raise ValueError("Spoiler ranges must be a list.")

    validated_ranges = []

    for item in ranges:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("Each spoiler range must contain start and end.")

        start, end = item

        if type(start) is not int or type(end) is not int:
            raise ValueError("Spoiler positions must be integers.")

        text_length = len(text.encode("utf-16-le")) // 2

        if start < 0 or end <= start or end > text_length:
            raise ValueError("Invalid spoiler range.")

        validated_ranges.append([start, end])

    validated_ranges.sort(key=lambda item: item[0])

    for index in range(1, len(validated_ranges)):
        previous_end = validated_ranges[index - 1][1]
        current_start = validated_ranges[index][0]

        if current_start < previous_end:
            raise ValueError("Spoiler ranges cannot overlap.")

    return validated_ranges

@api_view(["GET", "POST"])
def comments(request, video_id):
    messages = get_messages(request)
    video = get_object_or_404(
        Video,
        id=video_id
    )

    if request.method == "GET":

        comments = Comment.objects.filter(
            video=video
        ).select_related(
            "user", "parent"
        ).order_by("-created_at")

        data = []

        for comment in comments:

            data.append({
                "id": comment.id,
                "user_id": comment.user.id,
                "username": comment.user.username,
                "profile_image": (
                    request.build_absolute_uri(
                        comment.user.profile.profile_image.url
                    )
                    if hasattr(comment.user, "profile")
                    and comment.user.profile.profile_image
                    else None
                ),
                "text": comment.text,
                "is_question": comment.is_question,
                "spoiler_ranges": comment.spoiler_ranges,
                "is_removed": comment.is_removed,
                "parent_comment_id": comment.parent_id,
                "created_at": comment.created_at.isoformat(),
                "likes_count": comment.likes.count(),
                "dislikes_count": comment.dislikes.count(),
                "is_liked": (
                    request.user.is_authenticated
                    and CommentLike.objects.filter(
                        user=request.user,
                        comment=comment
                    ).exists()
                ),

                "is_disliked": (
                    request.user.is_authenticated
                    and CommentDislike.objects.filter(
                        user=request.user,
                        comment=comment
                    ).exists()
                ),
            })

        return Response(data)

    if request.method == "POST":

        if not request.user.is_authenticated:

            return Response(
                {"error": messages["authentication_required"]},
                status=status.HTTP_401_UNAUTHORIZED
            )

        text = request.data.get("text", "").strip()

        if not text:

            return Response(
                {"error": messages["comment_text_required"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(text) > 1000:

            return Response(
                {"error": messages["comment_too_long"]},
                status=status.HTTP_400_BAD_REQUEST
            )

        is_question = request.data.get("is_question", False)

        if not isinstance(is_question, bool):
            return Response(
                {"error": "is_question must be a boolean."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            spoiler_ranges = validate_spoiler_ranges(
                request.data.get("spoiler_ranges", []),
                text
            )
        except ValueError as error:
            return Response(
                {"error": str(error)},
                status=status.HTTP_400_BAD_REQUEST
            )

        parent = None
        parent_id = request.data.get("parent_comment_id")

        if parent_id not in (None, ""):

            try:
                parent_id = int(parent_id)
            except (TypeError, ValueError):

                return Response(
                    {"error": messages["invalid_parent_comment_id"]},
                    status=status.HTTP_400_BAD_REQUEST
                )

            parent = get_object_or_404(
                Comment,
                id=parent_id,
                video=video
            )

            if parent.is_removed:
                return Response(
                    {"error": messages["reply_to_removed_comment"]},
                    status=status.HTTP_400_BAD_REQUEST
                )

        comment = Comment.objects.create(
            user=request.user,
            video=video,
            text=text,
            parent=parent,
            is_question=is_question,
            spoiler_ranges=spoiler_ranges
        )

        # Notify the video owner about a new top-level comment.
        if parent is None and video.user_id != request.user.id:
            notify_comment_interaction(
                recipient=video.user,
                sender=request.user,
                video=video,
                comment=comment,
                message=messages["notification_comment_on_video"].format(
                    username=request.user.username,
                    text=text[:180],
                ),
                notification_type=Notification.NotificationType.COMMENT
            )

        # Notify the parent comment's author about the reply.
        if parent and parent.user_id !=request.user.id:
            notify_comment_interaction(
                recipient=parent.user,
                sender=request.user,
                video=video,
                comment=comment,
                message=messages["notification_reply_to_comment"].format(
                    username=request.user.username,
                    text=text[:180],
                ),
                notification_type=Notification.NotificationType.COMMENT_REPLY
            )

        # Also notify the video owner if they are not the parent author.
        if (
            parent
            and video.user_id != request.user.id
            and video.user_id != parent.user_id
        ):
            notify_comment_interaction(
                recipient=video.user,
                sender=request.user,
                video=video,
                comment=comment,
                message=messages["notification_reply_on_video"].format(
                    username=request.user.username,
                    text=text[:180],
                ),
                notification_type=Notification.NotificationType.COMMENT_REPLY
            )

        return Response(
            {
                "message": messages["comment_added"],
                "comment": {
                    "id": comment.id,
                    "user_id": comment.user.id,
                    "username": comment.user.username,
                    "profile_image": (
                        request.build_absolute_uri(
                            comment.user.profile.profile_image.url
                        )
                        if hasattr(comment.user, "profile")
                        and comment.user.profile.profile_image
                        else None
                    ),
                    "text": comment.text,
                    "is_question": comment.is_question,
                    "spoiler_ranges": comment.spoiler_ranges,
                    "is_removed": comment.is_removed,
                    "parent_comment_id": comment.parent_id,
                    "created_at": comment.created_at.isoformat()
                }
            },
            status=status.HTTP_201_CREATED
        )

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def edit_comment_api(request, comment_id):
    messages = get_messages(request)
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": messages["comment_removed"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if comment.user_id != request.user.id:
        return Response(
            {"error": messages["edit_own_comment_only"]},
            status=status.HTTP_403_FORBIDDEN
        )

    text = request.data.get("text", "").strip()

    if not text:
        return Response(
            {"error": messages["comment_text_required"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(text) > 1000:
        return Response(
            {"error": messages["comment_too_long"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    is_question = request.data.get(
        "is_question",
        comment.is_question
    )

    if not isinstance(is_question, bool):
        return Response(
            {"error": "is_question must be a boolean."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if "spoiler_ranges" in request.data:
        try:
            spoiler_ranges = validate_spoiler_ranges(
                request.data["spoiler_ranges"],
                text
            )
        except ValueError as error:
            return Response(
                {"error": str(error)},
                status=status.HTTP_400_BAD_REQUEST
            )
    elif text != comment.text:
        # Old spoiler positions may no longer match the edited text.
        spoiler_ranges = []
    else:
        spoiler_ranges = comment.spoiler_ranges

    comment.text = text
    comment.is_question = is_question
    comment.spoiler_ranges = spoiler_ranges
    comment.save(
        update_fields=[
            "text",
            "is_question",
            "spoiler_ranges"
        ]
    )

    return Response({
        "message": messages["comment_updated"],
        "comment": {
            "id": comment.id,
            "text": comment.text,
            "parent_comment_id": comment.parent_id,
            "is_question": comment.is_question,
            "spoiler_ranges": comment.spoiler_ranges,
        }
    }, status=status.HTTP_200_OK)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_comment_api(request, comment_id):
    messages = get_messages(request)
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.user_id != request.user.id:
        return Response(
            {"error": messages["edit_own_comment_only"]},
            status=status.HTTP_403_FORBIDDEN
        )

    comment.delete()

    return Response(
        {"message": messages["comment_deleted"]},
        status=status.HTTP_200_OK
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def like_comment_api(request, comment_id):
    messages = get_messages(request)
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": messages["comment_removed"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    existing_like = CommentLike.objects.filter(
        user=request.user,
        comment=comment
    )

    if existing_like.exists():
        existing_like.delete()

        return Response({
            "liked": False,
            "disliked": False,
            "likes_count": comment.likes.count(),
            "dislikes_count": comment.dislikes.count(),
        })

    CommentDislike.objects.filter(
        user=request.user,
        comment=comment
    ).delete()

    CommentLike.objects.create(
        user=request.user,
        comment=comment
    )

    if comment.user_id != request.user.id:
        preferences, _ = NotificationPreference.objects.get_or_create(
            user=comment.user
        )

        if preferences.comment_likes_enabled:
            Notification.objects.create(
                recipient=comment.user,
                sender=request.user,
                notification_type=Notification.NotificationType.COMMENT_LIKE,
                message=messages["notification_comment_liked"].format(
                    username=request.user.username,
                ),
                video=comment.video,
                comment=comment
            )

    return Response({
        "liked": True,
        "disliked": False,
        "likes_count": comment.likes.count(),
        "dislikes_count": comment.dislikes.count(),
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def dislike_comment_api(request, comment_id):
    messages = get_messages(request)
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": messages["comment_removed"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    existing_dislike = CommentDislike.objects.filter(
        user=request.user,
        comment=comment
    )

    if existing_dislike.exists():
        existing_dislike.delete()

        return Response({
            "liked": False,
            "disliked": False,
            "likes_count": comment.likes.count(),
            "dislikes_count": comment.dislikes.count(),
        })

    CommentLike.objects.filter(
        user=request.user,
        comment=comment
    ).delete()

    CommentDislike.objects.create(
        user=request.user,
        comment=comment
    )

    return Response({
        "liked": False,
        "disliked": True,
        "likes_count": comment.likes.count(),
        "dislikes_count": comment.dislikes.count(),
    })

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def unlike_comment_api(request, comment_id):
    messages = get_messages(request)
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": messages["comment_removed"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    CommentLike.objects.filter(
        user=request.user,
        comment=comment
    ).delete()

    return Response({
        "liked": False,
        "disliked": CommentDislike.objects.filter(
            user=request.user,
            comment=comment
        ).exists(),
        "likes_count": comment.likes.count(),
        "dislikes_count": comment.dislikes.count(),
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def report_comment_api(request, comment_id):
    messages = get_messages(request)
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": messages["comment_removed"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Users cannot report their own comments.
    if comment.user_id == request.user.id:
        return Response(
            {"error": messages["report_own_comment"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    reason = request.data.get("reason", "").strip()
    details = request.data.get("details", "").strip()

    valid_reasons = [
        choice[0] for choice in CommentReport.Reason.choices
    ]

    if reason not in valid_reasons:
        return Response(
            {"error": messages["invalid_report_reason"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(details) > 500:
        return Response(
            {"error": messages["report_details_too_long"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    report, created = CommentReport.objects.get_or_create(
        reporter=request.user,
        comment=comment,
        defaults={
            "reason": reason,
            "details": details,
        }
    )

    if not created:
        return Response(
            {"error": messages["comment_already_reported"]},
            status=status.HTTP_409_CONFLICT
        )

    return Response(
        {
            "message": messages["comment_reported"],
            "report_id": report.id,
            "status": report.status,
        },
        status=status.HTTP_201_CREATED
    )



@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_live_chat_reports_api(request):
    reports = (
        LiveChatMessageReport.objects
        .select_related(
            "reporter",
            "chat_message",
            "chat_message__user",
            "chat_message__live_stream",
            "chat_message__live_stream__user",
        )
        .order_by("-created_at", "-id")
    )

    pending_count = LiveChatMessageReport.objects.filter(
        status=LiveChatMessageReport.Status.PENDING
    ).count()

    reviewed_count = LiveChatMessageReport.objects.filter(
        status=LiveChatMessageReport.Status.REVIEWED
    ).count()

    dismissed_count = LiveChatMessageReport.objects.filter(
        status=LiveChatMessageReport.Status.DISMISSED
    ).count()

    action_taken_count = LiveChatMessageReport.objects.filter(
        status=LiveChatMessageReport.Status.ACTION_TAKEN
    ).count()

    report_status = request.query_params.get("status", "all")

    allowed_statuses = [
        choice[0] for choice in LiveChatMessageReport.Status.choices
    ]

    if report_status != "all":
        if report_status not in allowed_statuses:
            return Response(
                {"error": "Invalid report status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reports = reports.filter(status=report_status)

    search = request.query_params.get("search", "").strip()

    if search:
        search_filter = (
            Q(chat_message__live_stream__title__icontains=search)
            | Q(chat_message__live_stream__user__username__icontains=search)
            | Q(chat_message__user__username__icontains=search)
            | Q(reporter__username__icontains=search)
            | Q(chat_message__message__icontains=search)
            | Q(reason__icontains=search)
            | Q(details__icontains=search)
        )

        if search.isdigit():
            search_filter |= (
                Q(id=int(search))
                | Q(chat_message_id=int(search))
                | Q(chat_message__live_stream_id=int(search))
            )

        reports = reports.filter(search_filter)

    ordering = request.query_params.get("ordering", "newest")

    if ordering == "newest":
        reports = reports.order_by("-created_at", "-id")
    elif ordering == "oldest":
        reports = reports.order_by("created_at", "id")
    else:
        return Response(
            {"error": "Invalid ordering."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        page_number = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))
    except (TypeError, ValueError):
        return Response(
            {"error": "Page and page_size must be integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if page_number < 1 or page_size < 1 or page_size > 100:
        return Response(
            {"error": "Invalid page or page_size."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    paginator = Paginator(reports, page_size)
    page_obj = paginator.get_page(page_number)

    data = [
        {
            "id": report.id,
            "live_id": report.chat_message.live_stream_id,
            "live_title": report.chat_message.live_stream.title,
            "channel_username": report.chat_message.live_stream.user.username,
            "message_id": report.chat_message_id,
            "message_author": report.chat_message.user.username,
            "message_text": report.chat_message.message,
            "message_is_removed": report.chat_message.is_removed,
            "reporter": report.reporter.username,
            "reason": report.reason,
            "reason_display": report.get_reason_display(),
            "details": report.details,
            "status": report.status,
            "status_display": report.get_status_display(),
            "created_at": report.created_at.isoformat(),
            "reviewed_at": (
                report.reviewed_at.isoformat()
                if report.reviewed_at
                else None
            ),
        }
        for report in page_obj.object_list
    ]

    return Response({
        "pending_count": pending_count,
        "reviewed_count": reviewed_count,
        "dismissed_count": dismissed_count,
        "action_taken_count": action_taken_count,
        "total_count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "page_size": page_size,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "reports": data,
    })


@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def update_admin_live_chat_report_api(request, report_id):
    report = get_object_or_404(
        LiveChatMessageReport,
        id=report_id,
    )

    new_status = request.data.get("status")

    allowed_statuses = [
        LiveChatMessageReport.Status.REVIEWED,
        LiveChatMessageReport.Status.DISMISSED,
    ]

    if new_status not in allowed_statuses:
        return Response(
            {"error": "Invalid report status."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    report.status = new_status
    report.reviewed_at = timezone.now()

    report.save(
        update_fields=["status", "reviewed_at"]
    )

    return Response(
        {
            "id": report.id,
            "status": report.status,
            "status_display": report.get_status_display(),
            "reviewed_at": report.reviewed_at.isoformat(),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def remove_admin_reported_live_chat_message_api(request, report_id):
    report = get_object_or_404(
        LiveChatMessageReport.objects.select_related("chat_message"),
        id=report_id,
    )

    chat_message = report.chat_message

    if chat_message.is_removed:
        return Response(
            {"error": "This chat message has already been removed."},
            status=status.HTTP_409_CONFLICT,
        )

    chat_message.is_removed = True
    chat_message.save(update_fields=["is_removed"])

    now = timezone.now()

    # Mark all reports for this message as action taken.
    LiveChatMessageReport.objects.filter(
        chat_message=chat_message,
    ).update(
        status=LiveChatMessageReport.Status.ACTION_TAKEN,
        reviewed_at=now,
    )

    return Response(
        {
            "message": "Reported chat message removed successfully.",
            "message_id": chat_message.id,
            "message_is_removed": True,
            "status": LiveChatMessageReport.Status.ACTION_TAKEN,
            "status_display": (
                LiveChatMessageReport.Status.ACTION_TAKEN.label
            ),
            "reviewed_at": now.isoformat(),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_live_reports_api(request):
    reports = (
        LiveStreamReport.objects
        .select_related("reporter", "live_stream", "live_stream__user")
        .order_by("-created_at", "-id")
    )

    pending_count = LiveStreamReport.objects.filter(
        status=LiveStreamReport.Status.PENDING
    ).count()

    reviewed_count = LiveStreamReport.objects.filter(
        status=LiveStreamReport.Status.REVIEWED
    ).count()

    dismissed_count = LiveStreamReport.objects.filter(
        status=LiveStreamReport.Status.DISMISSED
    ).count()

    action_taken_count = LiveStreamReport.objects.filter(
        status=LiveStreamReport.Status.ACTION_TAKEN
    ).count()

    report_status = request.query_params.get("status", "all")

    allowed_statuses = [
        choice[0] for choice in LiveStreamReport.Status.choices
    ]

    if report_status != "all":
        if report_status not in allowed_statuses:
            return Response(
                {"error": "Invalid report status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reports = reports.filter(status=report_status)

    search = request.query_params.get("search", "").strip()

    if search:
        search_filter = (
            Q(live_stream__title__icontains=search)
            | Q(live_stream__user__username__icontains=search)
            | Q(reporter__username__icontains=search)
            | Q(reason__icontains=search)
            | Q(details__icontains=search)
        )

        if search.isdigit():
            search_filter |= (
                Q(id=int(search))
                | Q(live_stream_id=int(search))
            )

        reports = reports.filter(search_filter)

    ordering = request.query_params.get("ordering", "newest")

    if ordering == "newest":
        reports = reports.order_by("-created_at", "-id")
    elif ordering == "oldest":
        reports = reports.order_by("created_at", "id")
    else:
        return Response(
            {"error": "Invalid ordering."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        page_number = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))
    except (TypeError, ValueError):
        return Response(
            {"error": "Page and page_size must be integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if page_number < 1 or page_size < 1 or page_size > 100:
        return Response(
            {"error": "Invalid page or page_size."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    paginator = Paginator(reports, page_size)
    page_obj = paginator.get_page(page_number)

    data = [
        {
            "id": report.id,
            "live_id": report.live_stream_id,
            "live_title": report.live_stream.title,
            "channel_username": report.live_stream.user.username,
            "reporter": report.reporter.username,
            "reason": report.reason,
            "reason_display": report.get_reason_display(),
            "details": report.details,
            "status": report.status,
            "status_display": report.get_status_display(),
            "created_at": report.created_at.isoformat(),
            "reviewed_at": (
                report.reviewed_at.isoformat()
                if report.reviewed_at
                else None
            ),
        }
        for report in page_obj.object_list
    ]

    return Response({
        "pending_count": pending_count,
        "reviewed_count": reviewed_count,
        "dismissed_count": dismissed_count,
        "action_taken_count": action_taken_count,
        "total_count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "page_size": page_size,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "reports": data,
    })


@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def update_admin_live_report_api(request, report_id):
    report = get_object_or_404(
        LiveStreamReport,
        id=report_id,
    )

    new_status = request.data.get("status")

    allowed_statuses = [
        LiveStreamReport.Status.REVIEWED,
        LiveStreamReport.Status.DISMISSED,
    ]

    if new_status not in allowed_statuses:
        return Response(
            {"error": "Invalid report status."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    report.status = new_status
    report.reviewed_at = timezone.now()

    report.save(
        update_fields=["status", "reviewed_at"]
    )

    return Response(
        {
            "id": report.id,
            "status": report.status,
            "status_display": report.get_status_display(),
            "reviewed_at": report.reviewed_at.isoformat(),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_reports_api(request):
    reports = (
        CommentReport.objects
        .select_related("reporter", "comment", "comment__user")
        .order_by("-created_at")
    )

    # Global pending count
    pending_count = CommentReport.objects.filter(
        status=CommentReport.Status.PENDING
    ).count()

    reviewed_count = CommentReport.objects.filter(
        status=CommentReport.Status.REVIEWED
    ).count()

    dismissed_count = CommentReport.objects.filter(
        status=CommentReport.Status.DISMISSED
    ).count()

    action_taken_count = CommentReport.objects.filter(
        status=CommentReport.Status.ACTION_TAKEN
    ).count()

    # Filter by status
    report_status = request.query_params.get("status", "all")

    allowed_statuses = [
        choice[0] for choice in CommentReport.Status.choices
    ]

    if report_status != "all":
        if report_status not in allowed_statuses:
            return Response(
                {"error": "Invalid report status."},
                status=status.HTTP_400_BAD_REQUEST
            )

        reports = reports.filter(status=report_status)

    # Search
    search = request.query_params.get("search", "").strip()

    if search:
        reports = reports.filter(
            Q(comment__user__username__icontains=search)
            | Q(reporter__username__icontains=search)
            | Q(comment__text__icontains=search)
            | Q(reason__icontains=search)
            | Q(id__icontains=search)
            | Q(comment_id__icontains=search)
        )

    # Ordering
    ordering = request.query_params.get("ordering", "newest")

    if ordering == "newest":
        reports = reports.order_by("-created_at", "-id")
    elif ordering == "oldest":
        reports = reports.order_by("created_at", "id")
    else:
        return Response(
            {"error": "Invalid ordering."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Pagination
    try:
        page_number = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))
    except (TypeError, ValueError):
        return Response(
            {"error": "Page and page_size must be integers."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if page_number < 1 or page_size < 1 or page_size > 100:
        return Response(
            {"error": "Invalid page or page_size."},
            status=status.HTTP_400_BAD_REQUEST
        )

    paginator = Paginator(reports, page_size)
    page_obj = paginator.get_page(page_number)

    data = [
        {
            "id": report.id,
            "comment_id": report.comment_id,
            "comment_author": report.comment.user.username,
            "comment_text": report.comment.text,
            "comment_is_removed": report.comment.is_removed,
            "reporter": report.reporter.username,
            "reason": report.reason,
            "reason_display": report.get_reason_display(),
            "details": report.details,
            "status": report.status,
            "status_display": report.get_status_display(),
            "created_at": report.created_at.isoformat(),
            "reviewed_at": (
                report.reviewed_at.isoformat()
                if report.reviewed_at
                else None
            ),
        }
        for report in page_obj.object_list
    ]

    return Response({
        "pending_count": pending_count,
        "reviewed_count": reviewed_count,
        "dismissed_count": dismissed_count,
        "action_taken_count": action_taken_count,
        "total_count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "page_size": page_size,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "reports": data,
    })

@api_view(["PATCH"])
@permission_classes([IsAdminUser])
def update_admin_report_api(request, report_id):
    report = get_object_or_404(CommentReport, id=report_id)

    new_status = request.data.get("status")

    allowed_statuses = [
        CommentReport.Status.REVIEWED,
        CommentReport.Status.DISMISSED,
    ]

    if new_status not in allowed_statuses:
        return Response(
            {
                "error": "Invalid report status."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    report.status = new_status
    report.reviewed_at = timezone.now()
    report.save(update_fields=["status", "reviewed_at"])

    return Response({
        "message": "Report status updated successfully.",
        "report_id": report.id,
        "status": report.status,
        "status_display": report.get_status_display(),
        "reviewed_at": report.reviewed_at.isoformat(),
    })

@api_view(["POST"])
@permission_classes([IsAdminUser])
def remove_reported_comment_api(request, report_id):
    report = get_object_or_404(
        CommentReport.objects.select_related("comment"),
        id=report_id
    )

    comment = report.comment

    if comment.is_removed:
        return Response(
            {"error": "This comment has already been removed."},
            status=status.HTTP_400_BAD_REQUEST
        )

    comment.text = "این کامنت به‌دلیل نقض مقررات حذف شد."
    comment.is_removed = True
    comment.save(update_fields=["text", "is_removed"])

    report.status = CommentReport.Status.ACTION_TAKEN
    report.reviewed_at = timezone.now()
    report.save(update_fields=["status", "reviewed_at"])

    return Response({
        "message": "Comment removed successfully.",
        "report_id": report.id,
        "comment_id": comment.id,
        "comment_text": comment.text,
        "comment_is_removed": comment.is_removed,
        "status": report.status,
        "status_display": report.get_status_display(),
        "reviewed_at": report.reviewed_at.isoformat(),
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_api(request):

    videos = Video.objects.filter(
        user=request.user
    ).order_by("-created_at")

    data = []

    for video in videos:

        likes_count = VideoReaction.objects.filter(
            video=video,
            reaction_type=VideoReaction.LIKE
        ).count()

        dislikes_count = VideoReaction.objects.filter(
            video=video,
            reaction_type=VideoReaction.DISLIKE
        ).count()

        comments_count = Comment.objects.filter(
            video=video
        ).count()

        data.append({
            "id": video.id,
            "title": video.title,
            "description": video.description,
            "thumbnail": (
                request.build_absolute_uri(
                    video.thumbnail.url
                )
                if video.thumbnail
                else None
            ),
            "video_file": request.build_absolute_uri(
                video.video_file.url
            ),
            "views_count": video.views_count,
            "likes_count": likes_count,
            "dislikes_count": dislikes_count,
            "comments_count": comments_count,
            "created_at": video.created_at,
        })

    subscribers_count = Subscription.objects.filter(
        channel=request.user
    ).count()

    following_count = Subscription.objects.filter(
        subscriber=request.user
    ).count()

    total_views = sum(
        video.views_count for video in videos
    )

    total_likes = sum(
        VideoReaction.objects.filter(
            video=video,
            reaction_type=VideoReaction.LIKE
        ).count()
        for video in videos
    )

    total_comments = sum(
        Comment.objects.filter(
            video=video
        ).count()
        for video in videos
    )

    return Response({
        "videos": data,
        "videos_count": len(data),
        "subscribers_count": subscribers_count,
        "following_count": following_count,
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
    })

def user_profile(request, user_id):

    user=get_object_or_404(
        User,
        id=user_id
    )

    videos=Video.objects.filter(
        user=user
    ).order_by("-created_at")

    subscribers_count=Subscription.objects.filter(
        channel=user
    ).count()

    is_subscribed=False

    if request.user.is_authenticated:

        is_subscribed=Subscription.objects.filter(
            subscriber=request.user,
            channel=user
        ).exists()

    return render(
        request,
        "videos/user_profile.html",
        {
            "profile_user":user,
            "videos":videos,
            "subscribers_count":subscribers_count,
            "is_subscribed":is_subscribed
        }
    )

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def edit_profile_api(request):
    user = request.user
    profile = getattr(user, "profile", None)

    if not profile:
        profile = Profile.objects.create(user=user)

    bio = request.data.get("bio")

    if bio is not None:
        profile.bio = bio

    old_profile_image_name = None

    if "profile_image" in request.FILES:

        if profile.profile_image:
            old_profile_image_name = profile.profile_image.name

        profile.profile_image = request.FILES["profile_image"]

    profile.save()

    if (
        old_profile_image_name
        and old_profile_image_name != profile.profile_image.name
    ):
        transaction.on_commit(
            lambda file_name=old_profile_image_name:
                delete_file_safely(file_name, "profile image")
        )

    return Response({
        "message": "Profile updated successfully.",
        "id": user.id,
        "username": user.username,
        "bio": profile.bio,
        "profile_image": (
            request.build_absolute_uri(profile.profile_image.url)
            if profile.profile_image
            else None
        ),
    })

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def change_username_api(request):
    messages = get_messages(request)
    new_username = request.data.get(
        "username", ""
    ).strip()

    if not new_username:
        return Response(
            {"error": messages["username_empty"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(
        username=new_username
    ).exclude(id=request.user.id).exists():
        return Response(
            {"error": messages["username_exists"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    request.user.username = new_username
    request.user.save(update_fields=["username"])

    return Response({
        "message": messages["username_updated"],
        "username": request.user.username
    })

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def change_password_api(request):
    messages = get_messages(request)
    current_password = request.data.get(
        "current_password", ""
    )

    new_password = request.data.get(
        "new_password", ""
    )

    password_confirm = request.data.get(
        "password_confirm", ""
    )

    user = request.user

    if not current_password or not new_password or not password_confirm:
        return Response(
            {"error": messages["all_fields_required"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not user.check_password(current_password):
        return Response(
            {"error": messages["current_password_incorrect"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if new_password != password_confirm:
        return Response(
            {"error": messages["new_passwords_mismatch"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(new_password) < 8:
        return Response(
            {"error": messages["password_too_short"]},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    return Response({
        "message": messages["password_updated"]
    })

@login_required
def toggle_subscription(request,user_id):

    channel=get_object_or_404(
        User,
        id=user_id
    )

    if channel==request.user:
        return redirect(
            "user_profile",
            user_id=user_id
        )

    subscription=Subscription.objects.filter(
        subscriber=request.user,
        channel=channel
    ).first()

    if subscription:

        subscription.delete()

    else:

        Subscription.objects.create(
            subscriber=request.user,
            channel=channel
        )

        notify_subscriber_milestone(channel)

    return redirect(
        "user_profile",
        user_id=user_id
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_video_api(request):

    title = request.data.get("title", "").strip()
    description = request.data.get("description", "").strip()
    video_file = request.FILES.get("video_file")
    thumbnail = request.FILES.get("thumbnail")
    category_id = request.data.get("category_id")

    if not title:
        return Response(
            {"error": "Title is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not video_file:
        return Response(
            {"error": "Video file is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    category = None

    if category_id:
        category = get_object_or_404(
            Category,
            id=category_id
        )

    video = Video.objects.create(
        title=title,
        description=description,
        video_file=video_file,
        thumbnail=thumbnail,
        category=category,
        user=request.user
    )

    video.duration = get_video_duration(video.video_file.path)
    video.save(update_fields=["duration"])

    # Generate HLS without re-encoding the source video.
    try:
        hls_playlist = generate_hls(
            video.video_file.path,
            settings.MEDIA_ROOT / "hls" / str(video.id),
        )

        logger.info(
            "HLS generated successfully for video %s: %s",
            video.id,
            hls_playlist,
        )

    except (HLSGenerationError, OSError) as error:
        # Keep the original video available as a fallback.
        logger.warning(
            "HLS generation skipped for video %s: %s",
            video.id,
            error,
        )

    notify_subscribers_new_video(video)

    return Response(
        {
            "message": "Video uploaded successfully.",
            "id": video.id,
            "title": video.title,
        },
        status=status.HTTP_201_CREATED
    )

@api_view(["GET"])
def category_list_api(request):

    categories = Category.objects.all().order_by("name")

    data = []

    for category in categories:

        data.append({
            "id": category.id,
            "name": category.name,
        })

    return Response(data)

@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def edit_video_api(request, video_id):

    video = get_object_or_404(
        Video,
        id=video_id,
        user=request.user
    )

    title = request.data.get("title")
    description = request.data.get("description")
    category_id = request.data.get("category")
    new_video_file = request.FILES.get("video_file")

    if title is not None:
        title = title.strip()

        if not title:
            return Response(
                {"error": "Title cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST
            )

    if new_video_file:
        error = validate_video_file(new_video_file)

        if error:
            return Response(
                {"error": error},
                status=status.HTTP_400_BAD_REQUEST
            )

    if title is not None:
        video.title = title

    if description is not None:
        video.description = description.strip()

    if category_id is not None:
        category = get_object_or_404(
            Category,
            id=category_id
        )

        video.category = category

    old_thumbnail_file_name = None

    new_thumbnail = request.FILES.get("thumbnail")

    if new_thumbnail:
        if video.thumbnail:
            old_thumbnail_file_name = video.thumbnail.name

        video.thumbnail = new_thumbnail

    old_video_file_name = None

    if new_video_file:
        old_video_file_name = video.video_file.name
        video.video_file = new_video_file

    video.save()

    # Delete the previous thumbnail after successful database save.
    if (
        old_thumbnail_file_name
        and old_thumbnail_file_name != video.thumbnail.name
    ):
        transaction.on_commit(
            lambda file_name=old_thumbnail_file_name:
                delete_file_safely(file_name, "thumbnail")
        )

    if new_video_file:
        # Update the video duration.
        video.duration = get_video_duration(video.video_file.path)
        video.save(update_fields=["duration"])

        # Generate HLS for the new source video.
        hls_dir = settings.MEDIA_ROOT / "hls" / str(video.id)
        try:
            hls_playlist = generate_hls(
                video.video_file.path,
                hls_dir,
            )

            logger.info(
                "HLS regenerated successfully for video %s: %s",
                video.id,
                hls_playlist,
            )

        except (HLSGenerationError, OSError) as error:
            logger.warning(
                "HLS regeneration skipped for video %s: %s",
                video.id,
                error,
            )
            # Remove stale HLS files if generation of the new source fails.
            try:
                if hls_dir.exists():
                    shutil.rmtree(hls_dir)

            except OSError:
                logger.exception(
                    "Failed to remove stale HLS files for video %s",
                    video.id,
                )

        # Delete the previous uploaded video file.
        if old_video_file_name and old_video_file_name != video.video_file.name:
            transaction.on_commit(
                lambda file_name=old_video_file_name:
                    delete_file_safely(file_name, "video")
            )

    return Response({
        "message": "Video updated successfully."
    })

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_video_api(request, video_id):

    video = get_object_or_404(
        Video,
        id=video_id,
        user=request.user
    )

    hls_dir = settings.MEDIA_ROOT / "hls" / str(video.id)

    # Keep the file names before deleting the database record.
    files_to_delete = []

    if video.video_file:
        files_to_delete.append(video.video_file.name)

    if video.thumbnail:
        files_to_delete.append(video.thumbnail.name)

    # Collect generated video quality files.
    quality_files = video.qualities.exclude(
        video_file=""
    ).values_list(
        "video_file",
        flat=True,
    )

    files_to_delete.extend(quality_files)

    # Collect subtitle files.
    subtitle_files = video.subtitles.exclude(
        subtitle_file=""
    ).values_list(
        "subtitle_file",
        flat=True,
    )

    files_to_delete.extend(subtitle_files)

    def delete_video_files():
        # Delete the original video and thumbnail.
        for file_name in files_to_delete:
            try:
                default_storage.delete(file_name)

            except Exception:
                logger.exception(
                    "Failed to delete media file: %s",
                    file_name,
                )

        # Delete HLS playlist and segments.
        try:
            if hls_dir.exists():
                shutil.rmtree(hls_dir)

                logger.info(
                    "HLS files deleted for video %s",
                    video_id,
                )

        except OSError:
            logger.exception(
                "Failed to delete HLS files for video %s",
                video_id,
            )

    # Delete the database record first.
    with transaction.atomic():
        video.delete()
        transaction.on_commit(delete_video_files)

    return Response(
        {
            "message": "Video deleted successfully."
        },
        status=status.HTTP_200_OK
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notifications_api(request):
    notifications = Notification.objects.filter(
        recipient=request.user
    ).select_related(
        "sender", "video", "comment"
    ).order_by("-created_at")

    data = [
        {
            "id": notification.id,
            "sender": (
                notification.sender.username
                if notification.sender else None
            ),
            "type": notification.notification_type,
            "message": notification.message,
            "interaction_count": notification.interaction_count,
            "video_id": notification.video_id,
            "video_title": (
                notification.video.title
                if notification.video else None
            ),
            "comment_id": notification.comment_id,
            "is_read": notification.is_read,
            "created_at": notification.created_at,
        }
        for notification in notifications
    ]

    return Response(data)

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def mark_notification_read_api(request, notification_id):
    try:
        notification = Notification.objects.get(
            id=notification_id,
            recipient=request.user
        )
    except Notification.DoesNotExist:
        return Response(
            {"error": "Notification not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    notification.is_read = True
    notification.save(update_fields=["is_read"])

    return Response({
        "message": "Notification marked as read.",
        "id": notification.id,
        "is_read": notification.is_read
    })

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    updated_count = Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).update(is_read=True)

    return Response({
        "message": "All notifications marked as read.",
        "updated_count": updated_count
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unread_notifications_count_api(request):
    unread_count = Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()

    return Response({
        "unread_count": unread_count
    })

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def notification_preferences_api(request):
    preferences, _ = NotificationPreference.objects.get_or_create(
        user=request.user
    )

    editable_fields = [
        "subscriptions_enabled",
        "video_likes_enabled",
        "comments_enabled",
        "comment_replies_enabled",
        "comment_likes_enabled",
        "milestones_enabled",
        "activity_digest_enabled",
        "comments_digest_threshold",
        "new_videos_enabled",
    ]

    if request.method == "GET":
        data = {
            field: getattr(preferences, field)
            for field in editable_fields
        }
        data["pending_comment_interactions"] = (
            preferences.pending_comment_interactions
        )
        return Response(data)

    data = request.data

    # Reject unknown fields.
    unknown_fields = set(data.keys()) - set(editable_fields)
    if unknown_fields:
        return Response(
            {
                "error": "Unknown settings.",
                "fields": sorted(unknown_fields),
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    boolean_fields = [
        "subscriptions_enabled",
        "video_likes_enabled",
        "comments_enabled",
        "comment_replies_enabled",
        "comment_likes_enabled",
        "milestones_enabled",
        "activity_digest_enabled",
        "new_videos_enabled",
    ]

    for field in boolean_fields:
        if field in data and not isinstance(data[field], bool):
            return Response(
                {"error": f"{field} must be true or false."},
                status=status.HTTP_400_BAD_REQUEST
            )

    if "comments_digest_threshold" in data:
        threshold = data["comments_digest_threshold"]

        # bool is a subclass of int in Python, so reject it explicitly.
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, int)
            or not 1 <= threshold <= 10000
        ):
            return Response(
                {
                    "error": (
                        "comments_digest_threshold must be an integer "
                        "between 1 and 10000."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

    for field, value in data.items():
        setattr(preferences, field, value)

    preferences.save()

    response_data = {
        field: getattr(preferences, field)
        for field in editable_fields
    }
    response_data["pending_comment_interactions"] = (
        preferences.pending_comment_interactions
    )

    return Response(response_data, status=status.HTTP_200_OK)

def create_milestone_notification(channel, subscriber_count):
    milestones = [10, 50, 100]

    preferences, _ = NotificationPreference.objects.get_or_create(
        user=channel
    )

    if not preferences.milestones_enabled:
        return

    for milestone in milestones:
        if subscriber_count < milestone:
            continue

        milestone_record, created = SubscriberMilestone.objects.get_or_create(
            user=channel,
            milestone=milestone
        )

        if not created:
            continue

        Notification.objects.create(
            recipient=channel,
            sender=None,
            notification_type=Notification.NotificationType.MILESTONE,
            message=(
                f"Congratulations! Your channel reached "
                f"{milestone} subscribers!"
            )
        )

def notify_subscriber_milestone(channel):
    subscriber_count = Subscription.objects.filter(
        channel=channel
    ).count()

    create_milestone_notification(channel, subscriber_count)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_all_notifications(request):
    deleted_count, _ = Notification.objects.filter(
        recipient=request.user
    ).delete()

    return Response({
        "message": "All notifications deleted successfully.",
        "deleted_count": deleted_count
    })

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_notification(request, notification_id):
    try:
        notification = Notification.objects.get(
            id=notification_id,
            recipient=request.user
        )
    except Notification.DoesNotExist:
        return Response(
            {"error": "Notification not found."},
            status=404
        )

    notification.delete()

    return Response({
        "message": "Notification deleted successfully."
    })

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_account_api(request):
    messages = get_messages(request)
    user = request.user
    # Require password confirmation before irreversible deletion.
    password = request.data.get("password", "")

    if not password:
        return Response(
            {"error": messages["password_required_delete"]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not user.check_password(password):
        return Response(
            {"error": messages["incorrect_password"]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    files_to_delete = []
    hls_dirs = []

    # Collect all videos and their related media.
    videos = list(
        Video.objects.filter(user=user).prefetch_related(
            "qualities",
            "subtitles",
        )
    )

    for video in videos:

        # Original video.
        if video.video_file:
            files_to_delete.append(video.video_file.name)

        # Thumbnail.
        if video.thumbnail:
            files_to_delete.append(video.thumbnail.name)

        # Generated video qualities.
        for quality in video.qualities.all():
            if quality.video_file:
                files_to_delete.append(
                    quality.video_file.name
                )

        # Subtitles.
        for subtitle in video.subtitles.all():
            if subtitle.subtitle_file:
                files_to_delete.append(
                    subtitle.subtitle_file.name
                )

        # HLS directory.
        hls_dirs.append(
            settings.MEDIA_ROOT / "hls" / str(video.id)
        )

    # Profile image.
    profile = getattr(user, "profile", None)

    if profile and profile.profile_image:
        files_to_delete.append(profile.profile_image.name)

    def delete_media_files():

        # Delete files stored through Django's storage system.
        for file_name in files_to_delete:
            try:
                default_storage.delete(file_name)

            except Exception:
                logger.exception(
                    "Failed to delete media file: %s",
                    file_name,
                )

        # Delete HLS directories.
        for hls_dir in hls_dirs:
            try:
                if hls_dir.is_symlink():
                    logger.warning(
                        "Skipping HLS symlink: %s",
                        hls_dir,
                    )

                elif hls_dir.is_dir():
                    shutil.rmtree(hls_dir)

                    logger.info(
                        "HLS directory deleted: %s",
                        hls_dir,
                    )

            except OSError:
                logger.exception(
                    "Failed to delete HLS directory: %s",
                    hls_dir,
                )

    # Delete the database records first. Remove media only after commit.
    with transaction.atomic():
        user.delete()
        transaction.on_commit(delete_media_files)

    return Response(
        {"message": messages["account_deleted"]},
        status=status.HTTP_200_OK,
    )

def get_video_duration(video_path):
    ffprobe_path = shutil.which("ffprobe")

    if not ffprobe_path:
        logger.warning("FFprobe was not found on the system PATH.")
        return 0

    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return max(0, float(result.stdout.strip()))

    except (subprocess.SubprocessError, ValueError, OSError) as error:
        logger.warning(
            "Could not extract video duration from %s: %s",
            video_path,
            error,
        )
        return 0

def delete_file_safely(file_name, file_type):
    try:
        default_storage.delete(file_name)
    except Exception:
        logger.exception(
            "Failed to delete previous %s: %s",
            file_type,
            file_name,
        )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_live_stream_api(request):

    title = request.data.get("title", "")
    description = request.data.get("description", "")

    if not isinstance(title, str):
        title = ""

    if not isinstance(description, str):
        description = ""

    title = title.strip()
    description = description.strip()
    thumbnail = request.FILES.get("thumbnail")
    thumbnail_error = validate_live_thumbnail_file(thumbnail)

    if thumbnail_error:
        return Response(
            {"error": thumbnail_error},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not title:
        return Response(
            {"error": "Live stream title is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(title) > 200:
        return Response(
            {"error": "Title cannot exceed 200 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if LiveStream.objects.filter(
        user=request.user,
        status__in=[
            LiveStream.Status.DRAFT,
            LiveStream.Status.LIVE,
        ],
    ).exists():
        return Response(
            {"error": "You already have an active live stream."},
            status=status.HTTP_409_CONFLICT,
        )

    # Generate a strong, one-time publishing secret.
    stream_secret = secrets.token_urlsafe(32)

    stream_key_hash = hashlib.sha256(
        stream_secret.encode("utf-8")
    ).hexdigest()

    with transaction.atomic():
        live_stream = LiveStream.objects.create(
            user=request.user,
            title=title,
            description=description,
            thumbnail=thumbnail,
            stream_key_hash=stream_key_hash,
        )

    return Response(
        {
            "id": live_stream.id,
            "title": live_stream.title,
            "description": live_stream.description,
            "thumbnail": live_stream.thumbnail.url if live_stream.thumbnail else None,
            "status": live_stream.status,

            "rtmp_server": "rtmp://127.0.0.1:1935/live",

            # OBS appends this value to the RTMP server URL.
            # The password is sent as an RTMP query parameter.
            "obs_stream_key": (
                f"{live_stream.id}"
                f"?user=publisher&pass={stream_secret}"
            ),

            "hls_url": (
                f"/live/{live_stream.id}/index.m3u8"
            ),
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["GET"])
@permission_classes([AllowAny])
def live_stream_detail_api(request, live_id):

    queryset = LiveStream.objects.select_related(
        "user",
        "archive_video",
    )

    # Public users can access live and ended streams.
    # The owner can also access their own draft or failed stream.
    if request.user.is_authenticated:
        queryset = queryset.filter(
            Q(
                status__in=[
                    LiveStream.Status.LIVE,
                    LiveStream.Status.ENDED,
                ]
            )
            | Q(user=request.user)
        )
    else:
        queryset = queryset.filter(
            status__in=[
                LiveStream.Status.LIVE,
                LiveStream.Status.ENDED,
            ]
        )

    live_stream = get_object_or_404(
        queryset,
        pk=live_id,
    )

    archive_video = None

    if live_stream.archive_video_id:
        archive_video = {
            "id": live_stream.archive_video.id,
            "title": live_stream.archive_video.title,
        }

    return Response(
        {
            "id": live_stream.id,
            "title": live_stream.title,
            "description": live_stream.description,
            "thumbnail": live_stream.thumbnail.url if live_stream.thumbnail else None,
            "status": live_stream.status,

            "owner": {
                "id": live_stream.user_id,
                "username": live_stream.user.username,
            },

            "started_at": (
                live_stream.started_at.isoformat()
                if live_stream.started_at
                else None
            ),

            "ended_at": (
                live_stream.ended_at.isoformat()
                if live_stream.ended_at
                else None
            ),

            "archive_status": live_stream.archive_status,
            "archive_video": archive_video,

            "hls_url": (
                f"/live/{live_stream.id}/index.m3u8"
                if live_stream.status == LiveStream.Status.LIVE
                else None
            ),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([AllowAny])
def active_live_streams_api(request):
    live_streams = (
        LiveStream.objects
        .filter(status=LiveStream.Status.LIVE)
        .select_related("user")
        .order_by("-started_at", "-created_at")
    )

    data = [
        {
            "id": live_stream.id,
            "title": live_stream.title,
            "description": live_stream.description,
            "thumbnail": (
                request.build_absolute_uri(live_stream.thumbnail.url)
                if live_stream.thumbnail
                else None
            ),
            "owner": {
                "id": live_stream.user_id,
                "username": live_stream.user.username,
            },
            "started_at": (
                live_stream.started_at.isoformat()
                if live_stream.started_at
                else None
            ),
        }
        for live_stream in live_streams
    ]

    return Response(data, status=status.HTTP_200_OK)

@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def live_chat_api(request, live_id):

    live_stream = get_object_or_404(
        LiveStream.objects.select_related("user"),
        pk=live_id,
    )

    # Public access: live and ended streams.
    # Draft and failed streams: owner only.
    if live_stream.status not in [
        LiveStream.Status.LIVE,
        LiveStream.Status.ENDED,
    ]:
        if (
            not request.user.is_authenticated
            or live_stream.user_id != request.user.id
        ):
            return Response(
                {"error": "Stream not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    # Send a new message.
    if request.method == "POST":

        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if live_stream.status != LiveStream.Status.LIVE:
            return Response(
                {"error": "This live stream has ended."},
                status=status.HTTP_409_CONFLICT,
            )

        message = request.data.get("message", "")

        if not isinstance(message, str):
            return Response(
                {"error": "Invalid message."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = message.strip()

        if not message:
            return Response(
                {"error": "Message cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(message) > 500:
            return Response(
                {"error": "Message cannot exceed 500 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        chat_message = LiveChatMessage.objects.create(
            live_stream=live_stream,
            user=request.user,
            message=message,
        )

        return Response(
            {
                "id": chat_message.id,
                "username": request.user.username,
            "user_id": request.user.id,
            "is_own": True,
                "message": chat_message.message,
                "created_at": chat_message.created_at.isoformat(),
            "total_count": LiveChatMessage.objects.filter(
                live_stream=live_stream,
                is_removed=False,
            ).count(),
            },
            status=status.HTTP_201_CREATED,
        )

    # Fetch messages incrementally.
    after_value = request.query_params.get("after")
    after_id = None

    if after_value is not None:
        try:
            after_id = int(after_value)

            if after_id < 0:
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"error": "Invalid message cursor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    messages_query = LiveChatMessage.objects.filter(
        live_stream=live_stream,
        is_removed=False,
    ).select_related("user")

    if after_id is not None:
        messages = list(
            messages_query.filter(
                id__gt=after_id
            ).order_by("id")[:50]
        )
    else:
        messages = list(
            messages_query.order_by("-id")[:50]
        )

        messages.reverse()

    total_count = messages_query.count()

    result = [
        {
            "id": item.id,
            "user_id": item.user_id,
            "username": item.user.username,
            "is_own": (
                request.user.is_authenticated
                and item.user_id == request.user.id
            ),
            "message": item.message,
            "created_at": item.created_at.isoformat(),
        }
        for item in messages
    ]

    return Response(
        {
            "messages": result,
            "total_count": total_count,
            "next_after": (
                messages[-1].id
                if messages
                else after_id
            ),
        },
        status=status.HTTP_200_OK,
    )



@api_view(["POST"])
@permission_classes([IsAuthenticated])
def report_live_chat_message_api(request, live_id, message_id):
    live_stream = get_object_or_404(
        LiveStream.objects.filter(
            status__in=[
                LiveStream.Status.LIVE,
                LiveStream.Status.ENDED,
            ]
        ),
        pk=live_id,
    )

    chat_message = get_object_or_404(
        LiveChatMessage,
        pk=message_id,
        live_stream=live_stream,
    )

    if chat_message.is_removed:
        return Response(
            {"error": "This message is no longer available."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if chat_message.user_id == request.user.id:
        return Response(
            {"error": "You cannot report your own message."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reason = request.data.get("reason", "")
    details = request.data.get("details", "")

    if not isinstance(reason, str) or not isinstance(details, str):
        return Response(
            {"error": "Invalid report data."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reason = reason.strip()
    details = details.strip()

    valid_reasons = [
        choice[0] for choice in LiveChatMessageReport.Reason.choices
    ]

    if reason not in valid_reasons:
        return Response(
            {"error": "Invalid report reason."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(details) > 500:
        return Response(
            {"error": "Report details must be 500 characters or less."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    report, created = LiveChatMessageReport.objects.get_or_create(
        reporter=request.user,
        chat_message=chat_message,
        defaults={
            "reason": reason,
            "details": details,
        },
    )

    if not created:
        return Response(
            {"error": "You have already reported this message."},
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            "message": "Chat message report submitted successfully.",
            "report_id": report.id,
            "status": report.status,
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def report_live_stream_api(request, live_id):
    live_stream = get_object_or_404(
        LiveStream.objects.select_related("user"),
        pk=live_id,
    )

    if live_stream.status not in [
        LiveStream.Status.LIVE,
        LiveStream.Status.ENDED,
    ]:
        return Response(
            {"error": "This live stream is not available for reporting."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if live_stream.user_id == request.user.id:
        return Response(
            {"error": "You cannot report your own live stream."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reason = request.data.get("reason", "")
    details = request.data.get("details", "")

    if not isinstance(reason, str) or not isinstance(details, str):
        return Response(
            {"error": "Invalid report data."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reason = reason.strip()
    details = details.strip()

    valid_reasons = [
        choice[0] for choice in LiveStreamReport.Reason.choices
    ]

    if reason not in valid_reasons:
        return Response(
            {"error": "Invalid report reason."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(details) > 500:
        return Response(
            {"error": "Report details must be 500 characters or less."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    report, created = LiveStreamReport.objects.get_or_create(
        reporter=request.user,
        live_stream=live_stream,
        defaults={
            "reason": reason,
            "details": details,
        },
    )

    if not created:
        return Response(
            {"error": "You have already reported this live stream."},
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            "message": "Live stream report submitted successfully.",
            "report_id": report.id,
            "status": report.status,
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["GET", "POST", "DELETE"])
@permission_classes([AllowAny])
def live_stream_reaction_api(request, live_id):

    live_stream = get_object_or_404(
        LiveStream.objects.select_related("user"),
        pk=live_id,
    )

    # Public access for live and ended streams.
    if live_stream.status not in [
        LiveStream.Status.LIVE,
        LiveStream.Status.ENDED,
    ]:
        if (
            not request.user.is_authenticated
            or live_stream.user_id != request.user.id
        ):
            return Response(
                {"error": "Stream not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    # Only authenticated users can modify reactions.
    if request.method in ["POST", "DELETE"]:

        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if live_stream.status != LiveStream.Status.LIVE:
            return Response(
                {"error": "This live stream has ended."},
                status=status.HTTP_409_CONFLICT,
            )

    # Get the current user's reaction.
    user_reaction = None

    if request.user.is_authenticated:
        user_reaction = LiveStreamReaction.objects.filter(
            live_stream=live_stream,
            user=request.user,
        ).first()

    # Remove the current user's reaction.
    if request.method == "DELETE":
        if user_reaction:
            user_reaction.delete()

        user_reaction = None

    # Create or update a reaction.
    elif request.method == "POST":

        reaction_type = request.data.get("reaction", "")

        if not isinstance(reaction_type, str):
            reaction_type = ""

        reaction_type = reaction_type.strip().lower()

        if reaction_type not in [
            LiveStreamReaction.LIKE,
            LiveStreamReaction.DISLIKE,
        ]:
            return Response(
                {"error": "Invalid reaction."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user_reaction, created = (
                LiveStreamReaction.objects.get_or_create(
                    live_stream=live_stream,
                    user=request.user,
                    defaults={
                        "reaction_type": reaction_type,
                    },
                )
            )

            if (
                not created
                and user_reaction.reaction_type != reaction_type
            ):
                user_reaction.reaction_type = reaction_type
                user_reaction.save(
                    update_fields=["reaction_type"]
                )

    # Count reactions.
    likes_count = LiveStreamReaction.objects.filter(
        live_stream=live_stream,
        reaction_type=LiveStreamReaction.LIKE,
    ).count()

    dislikes_count = LiveStreamReaction.objects.filter(
        live_stream=live_stream,
        reaction_type=LiveStreamReaction.DISLIKE,
    ).count()

    return Response(
        {
            "likes_count": likes_count,
            "dislikes_count": dislikes_count,
            "user_reaction": (
                user_reaction.reaction_type
                if user_reaction
                else None
            ),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@permission_classes([AllowAny])
def mediamtx_auth_api(request):

    # Only the local MediaMTX process may use this endpoint.
    remote_ip = request.META.get("REMOTE_ADDR", "")
    forwarded_ip = request.META.get("HTTP_X_REAL_IP", "")
    allowed_ips = {"127.0.0.1", "::1"}

    if (
        remote_ip not in allowed_ips
        or (
            forwarded_ip
            and forwarded_ip not in allowed_ips
        )
    ):
        return Response(
            {"error": "Forbidden."},
            status=status.HTTP_403_FORBIDDEN,
        )

    action = request.data.get("action", "")
    protocol = request.data.get("protocol", "")
    path = str(request.data.get("path", "")).strip("/")

    # Only accept live/<numeric-id>.
    match = re.fullmatch(r"live/([1-9]\d*)", path)

    if not match:
        return Response(
            {"error": "Invalid stream path."},
            status=status.HTTP_403_FORBIDDEN,
        )

    live_stream = LiveStream.objects.filter(
        pk=int(match.group(1))
    ).first()

    if live_stream is None:
        return Response(
            {"error": "Stream not found."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # OBS publishing authentication.
    if action == "publish" and protocol == "rtmp":

        username = request.data.get("user", "")
        password = request.data.get("password", "")

        if username != "publisher" or not password:
            return Response(
                {"error": "Invalid publishing credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        supplied_hash = hashlib.sha256(
            password.encode("utf-8")
        ).hexdigest()

        if not secrets.compare_digest(
            supplied_hash,
            live_stream.stream_key_hash,
        ):
            return Response(
                {"error": "Invalid publishing credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if live_stream.status not in {
            LiveStream.Status.DRAFT,
            LiveStream.Status.LIVE,
        }:
            return Response(
                {"error": "This stream cannot be published."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Authentication only.
        # Actual LIVE status will be set by a MediaMTX event.
        return Response(status=status.HTTP_200_OK)

    # Public HLS playback authentication.
    if action == "read" and protocol == "hls":

        if live_stream.status == LiveStream.Status.LIVE:
            return Response(status=status.HTTP_200_OK)

        return Response(
            {"error": "Stream is not live."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response(
        {"error": "Action not allowed."},
        status=status.HTTP_403_FORBIDDEN,
    )

@api_view(["POST"])
@permission_classes([AllowAny])
def mediamtx_event_api(request):

    remote_ip = request.META.get("REMOTE_ADDR", "")
    forwarded_ip = request.META.get("HTTP_X_REAL_IP", "")

    allowed_ips = {"127.0.0.1", "::1"}

    if (
        remote_ip not in allowed_ips
        or (
            forwarded_ip
            and forwarded_ip not in allowed_ips
        )
    ):
        return Response(
            {"error": "Forbidden."},
            status=status.HTTP_403_FORBIDDEN,
        )

    expected_token = settings.LIVE_WEBHOOK_TOKEN or ""
    supplied_token = request.META.get(
        "HTTP_X_LIVE_WEBHOOK_TOKEN",
        "",
    )

    if (
        not expected_token
        or not supplied_token
        or not secrets.compare_digest(
            expected_token,
            supplied_token,
        )
    ):
        return Response(
            {"error": "Invalid webhook token."},
            status=status.HTTP_403_FORBIDDEN,
        )

    event = str(request.data.get("event", "")).strip()
    path = str(request.data.get("path", "")).strip("/")
    source_id = request.data.get("source_id", "")

    match = re.fullmatch(r"live/([1-9]\d*)", path)

    if not match:
        return Response(
            {"error": "Invalid stream path."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if event not in {"online", "offline"}:
        return Response(
            {"error": "Invalid event."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if (
        not isinstance(source_id, str)
        or not source_id.strip()
        or len(source_id.strip()) > 128
    ):
        return Response(
            {"error": "Invalid source ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    source_id = source_id.strip()

    with transaction.atomic():

        live_stream = (
            LiveStream.objects
            .select_for_update()
            .filter(id=int(match.group(1)))
            .first()
        )

        if live_stream is None:
            return Response(
                {"error": "Live stream not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if event == "online":

            if live_stream.status not in {
                LiveStream.Status.DRAFT,
                LiveStream.Status.LIVE,
            }:
                return Response(
                    {"error": "Live stream cannot become online."},
                    status=status.HTTP_409_CONFLICT,
                )

            if live_stream.status == LiveStream.Status.DRAFT:
                live_stream.started_at = timezone.now()

            live_stream.status = LiveStream.Status.LIVE
            live_stream.active_source_id = source_id

            live_stream.save(
                update_fields=[
                    "status",
                    "started_at",
                    "active_source_id",
                    "updated_at",
                ]
            )

            return Response(
                {
                    "event": "online",
                    "id": live_stream.id,
                    "status": live_stream.status,
                    "source_id": live_stream.active_source_id,
                },
                status=status.HTTP_200_OK,
            )

        # Make repeated offline callbacks safe.
        if live_stream.status == LiveStream.Status.ENDED:
            return Response(
                {
                    "event": "offline",
                    "id": live_stream.id,
                    "status": live_stream.status,
                },
                status=status.HTTP_200_OK,
            )

        if live_stream.status != LiveStream.Status.LIVE:
            return Response(
                {"error": "Live stream is not active."},
                status=status.HTTP_409_CONFLICT,
            )

        # Ignore an offline event from an older publisher.
        if live_stream.active_source_id != source_id:
            return Response(
                {
                    "event": "offline",
                    "ignored": True,
                    "reason": "A different publisher source is active.",
                },
                status=status.HTTP_200_OK,
            )

        live_stream.status = LiveStream.Status.ENDED
        live_stream.ended_at = timezone.now()
        live_stream.active_source_id = ""

        live_stream.save(
            update_fields=[
                "status",
                "ended_at",
                "active_source_id",
                "updated_at",
            ]
        )

        return Response(
            {
                "event": "offline",
                "id": live_stream.id,
                "status": live_stream.status,
            },
            status=status.HTTP_200_OK,
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def mediamtx_archive_api(request):

    from pathlib import Path
    import time

    # Only allow local MediaMTX requests.
    remote_ip = request.META.get("REMOTE_ADDR", "")
    forwarded_ip = request.META.get("HTTP_X_REAL_IP", "")

    allowed_ips = {"127.0.0.1", "::1"}

    if (
        remote_ip not in allowed_ips
        or (
            forwarded_ip
            and forwarded_ip not in allowed_ips
        )
    ):
        return Response(
            {"error": "Forbidden."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Verify the private webhook token.
    expected_token = settings.LIVE_WEBHOOK_TOKEN or ""
    supplied_token = request.META.get(
        "HTTP_X_LIVE_WEBHOOK_TOKEN",
        "",
    )

    if (
        not expected_token
        or not supplied_token
        or not secrets.compare_digest(
            expected_token,
            supplied_token,
        )
    ):
        return Response(
            {"error": "Invalid webhook token."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Accept only live/<numeric-id>.
    stream_path = str(
        request.data.get("path", "")
    ).strip("/")

    match = re.fullmatch(
        r"live/([1-9]\d*)",
        stream_path,
    )

    if not match:
        return Response(
            {"error": "Invalid stream path."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stream_id = int(match.group(1))

    # Lock the stream and prevent duplicate archive processing.
    with transaction.atomic():

        live_stream = (
            LiveStream.objects
            .select_for_update()
            .select_related("user")
            .filter(pk=stream_id)
            .first()
        )

        if live_stream is None:
            return Response(
                {"error": "Live stream not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if (
            live_stream.archive_video_id
            or live_stream.archive_status
            == LiveStream.ArchiveStatus.COMPLETED
        ):
            return Response(
                {
                    "event": "archive",
                    "id": stream_id,
                    "status": "completed",
                    "video_id": live_stream.archive_video_id,
                },
                status=status.HTTP_200_OK,
            )

        if (
            live_stream.archive_status
            == LiveStream.ArchiveStatus.PROCESSING
        ):
            return Response(
                {
                    "event": "archive",
                    "id": stream_id,
                    "status": "processing",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        if (
            live_stream.status != LiveStream.Status.ENDED
            or live_stream.active_source_id
        ):
            return Response(
                {"error": "Stream has not ended safely."},
                status=status.HTTP_409_CONFLICT,
            )

        live_stream.archive_status = (
            LiveStream.ArchiveStatus.PROCESSING
        )

        live_stream.save(
            update_fields=[
                "archive_status",
                "updated_at",
            ]
        )

    video = None
    archive_name = None
    temporary_files = []

    try:

        # Build the recording directory from the trusted stream ID.
        recording_base = (
            Path(settings.MEDIA_ROOT)
            / "live_recordings"
            / "live"
        ).resolve()

        recording_dir = (
            recording_base / str(stream_id)
        ).resolve()

        if recording_base not in recording_dir.parents:
            raise RuntimeError(
                "Invalid recording directory."
            )

        if not recording_dir.is_dir():
            raise FileNotFoundError(
                "Recording directory does not exist."
            )

        # Wait until all recording files have stable sizes.
        deadline = time.monotonic() + 30
        previous_snapshot = None
        stable_checks = 0
        recording_files = []

        while time.monotonic() < deadline:

            recording_files = sorted(
                (
                    path
                    for path in recording_dir.glob("*.mp4")
                    if (
                        path.is_file()
                        and not path.name.startswith(".archive-")
                    )
                ),
                key=lambda path: path.name,
            )

            snapshot = tuple(
                (
                    path.name,
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                )
                for path in recording_files
            )

            if (
                snapshot
                and all(item[1] > 0 for item in snapshot)
            ):
                if snapshot == previous_snapshot:
                    stable_checks += 1
                else:
                    stable_checks = 0

                if stable_checks >= 2:
                    break

            else:
                stable_checks = 0

            previous_snapshot = snapshot
            time.sleep(1)

        else:
            raise RuntimeError(
                "Recording files are missing or not stable."
            )

        if not recording_files:
            raise RuntimeError(
                "No completed recording files were found."
            )

        logger.info(
            "Found %s completed recording segments for live %s.",
            len(recording_files),
            stream_id,
        )

        # One segment can be used directly.
        archive_source = recording_files[0]

        # Merge multiple segments without re-encoding.
        if len(recording_files) > 1:

            ffmpeg_path = shutil.which("ffmpeg")

            if not ffmpeg_path:
                raise RuntimeError(
                    "FFmpeg was not found."
                )

            concat_file = (
                recording_dir
                / f".archive-concat-{secrets.token_hex(8)}.txt"
            )

            merged_file = (
                recording_dir
                / f".archive-merged-{secrets.token_hex(8)}.mp4"
            )

            temporary_files.extend(
                [concat_file, merged_file]
            )

            manifest_lines = []

            for segment in recording_files:

                escaped_path = (
                    segment.resolve()
                    .as_posix()
                    .replace("'", "'\\''")
                )

                manifest_lines.append(
                    f"file '{escaped_path}'"
                )

            concat_file.write_text(
                "\n".join(manifest_lines),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    ffmpeg_path,
                    "-hide_banner",
                    "-loglevel", "error",
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_file),
                    "-map", "0:v:0",
                    "-map", "0:a:0?",
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(merged_file),
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )

            if (
                result.returncode != 0
                or not merged_file.is_file()
                or merged_file.stat().st_size == 0
            ):
                raise RuntimeError(
                    "Recording segments could not be merged: "
                    f"{(result.stderr or '')[-1500:]}"
                )

            archive_source = merged_file

        # Calculate duration before creating the Video.
        duration = get_video_duration(
            str(archive_source)
        )

        if duration <= 0:
            raise RuntimeError(
                "Could not determine archive duration."
            )

        # Create a permanent Video file.
        video = Video(
            user=live_stream.user,
            title=live_stream.title,
            description=live_stream.description or "",
        )

        archive_name = (
            f"live_{stream_id}_{secrets.token_hex(6)}.mp4"
        )

        with archive_source.open("rb") as source_file:
            video.video_file.save(
                archive_name,
                File(source_file),
                save=False,
            )

        video.duration = duration
        video.save()

        # Attach the Video to its LiveStream.
        with transaction.atomic():

            locked_stream = (
                LiveStream.objects
                .select_for_update()
                .get(pk=stream_id)
            )

            if locked_stream.archive_video_id:
                raise RuntimeError(
                    "An archive video is already attached."
                )

            if (
                locked_stream.status != LiveStream.Status.ENDED
                or locked_stream.active_source_id
            ):
                raise RuntimeError(
                    "Stream state changed during archive processing."
                )

            locked_stream.archive_video = video

            locked_stream.save(
                update_fields=[
                    "archive_video",
                    "updated_at",
                ]
            )

        # Generate HLS without re-encoding.
        try:
            hls_playlist = generate_hls(
                video.video_file.path,
                Path(settings.MEDIA_ROOT)
                / "hls"
                / str(video.id),
            )

            logger.info(
                "HLS generated for archive video %s: %s",
                video.id,
                hls_playlist,
            )

        except (HLSGenerationError, OSError) as error:
            # The original video remains available as a fallback.
            logger.warning(
                "HLS generation failed for archive video %s: %s",
                video.id,
                error,
            )

        # Mark the archive as completed.
        with transaction.atomic():

            locked_stream = (
                LiveStream.objects
                .select_for_update()
                .get(pk=stream_id)
            )

            locked_stream.archive_status = (
                LiveStream.ArchiveStatus.COMPLETED
            )

            locked_stream.save(
                update_fields=[
                    "archive_status",
                    "updated_at",
                ]
            )

        # Notify subscribers, without invalidating the archive.
        try:
            notify_subscribers_new_video(video)

        except Exception:
            logger.exception(
                "Subscriber notification failed for archive video %s.",
                video.id,
            )

        logger.info(
            "Live archive completed. Live ID: %s, Video ID: %s",
            stream_id,
            video.id,
        )

        return Response(
            {
                "event": "archive",
                "id": stream_id,
                "status": "completed",
                "video_id": video.id,
                "title": video.title,
                "duration": video.duration,
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception:

        logger.exception(
            "Live archive processing failed for stream %s.",
            stream_id,
        )

        # Remove an incomplete Video and its stored file.
        if video is not None:

            stored_name = video.video_file.name

            if video.pk:
                video.delete()

            if stored_name:
                delete_file_safely(
                    stored_name,
                    "live archive",
                )

            if video.pk:
                hls_dir = (
                    Path(settings.MEDIA_ROOT)
                    / "hls"
                    / str(video.pk)
                )

                shutil.rmtree(
                    hls_dir,
                    ignore_errors=True,
                )

        LiveStream.objects.filter(
            pk=stream_id,
            archive_status=LiveStream.ArchiveStatus.PROCESSING,
        ).update(
            archive_status=LiveStream.ArchiveStatus.FAILED,
            updated_at=timezone.now(),
        )

        return Response(
            {"error": "Archive processing failed."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    finally:

        for temporary_file in temporary_files:
            try:
                temporary_file.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "Could not remove temporary archive file: %s",
                    temporary_file,
                )
