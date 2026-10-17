from django.shortcuts import render,get_object_or_404,redirect # type: ignore
from .models import CommentDislike, CommentReport, Video,VideoReaction,Category,Subscription,Profile,VideoView
from .models import Comment, CommentLike, Notification, NotificationPreference,SubscriberMilestone
from django.contrib.auth.decorators import login_required # type: ignore
from django.contrib.auth.models import User # type: ignore
from rest_framework.response import Response # type: ignore
from rest_framework import status # type: ignore
from django.contrib.auth import authenticate,login as auth_login # type: ignore
from django.contrib.auth import logout # type: ignore
from rest_framework_simplejwt.tokens import RefreshToken # type: ignore
from rest_framework.permissions import IsAuthenticated,IsAdminUser # type: ignore
from rest_framework.decorators import api_view,permission_classes # type: ignore
from django.db.models import Q # type: ignore
from django.core.paginator import Paginator # type: ignore
from django.utils import timezone # type: ignore
from datetime import timedelta
from rest_framework.pagination import PageNumberPagination # type: ignore
from django.db.models import F # type: ignore
from django.core.mail import send_mail # type: ignore
from django.conf import settings # type: ignore
from django.contrib.auth.tokens import default_token_generator # type: ignore
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode # type: ignore
from django.utils.encoding import force_bytes # type: ignore
from django.db import transaction # type: ignore
from django.core.files.storage import default_storage
import os
import logging

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

        Notification.objects.create(
            recipient=subscriber,
            sender=video.user,
            notification_type=Notification.NotificationType.NEW_VIDEO,
            message=f'{video.user.username} uploaded a new video: {video.title}',
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

    return Response({
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

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def react_to_video(request, video_id):
    video = get_object_or_404(Video, id=video_id)

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

def register(request):

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        # 1. Required fields
        if not username or not email or not password:
            return render(
                request,
                "videos/register.html",
                {
                    "error": "Username, email and password are required."
                }
            )

        # 2. Username length
        if len(username) < 3:
            return render(
                request,
                "videos/register.html",
                {
                    "error": "Username must be at least 3 characters."
                }
            )

        if len(username) > 30:
            return render(
                request,
                "videos/register.html",
                {
                    "error": "Username must be 30 characters or less."
                }
            )

        # 3. Email validation
        try:
            validate_email(email)
        except ValidationError:
            return render(
                request,
                "videos/register.html",
                {
                    "error": "Please enter a valid email address."
                }
            )

        # 4. Email uniqueness
        if User.objects.filter(email__iexact=email).exists():
            return render(
                request,
                "videos/register.html",
                {
                    "error": "This email is already registered."
                }
            )

        # 5. Username uniqueness
        if User.objects.filter(username=username).exists():
            return render(
                request,
                "videos/register.html",
                {
                    "error": "Username already exists."
                }
            )

        # 6. Password length
        if len(password) < 8:
            return render(
                request,
                "videos/register.html",
                {
                    "error": "Password must be at least 8 characters."
                }
            )

        # 7. Create user with email
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )

        # 8. Create profile
        Profile.objects.create(user=user)

        # 9. Log in automatically
        auth_login(request, user)

        return redirect("home")

    return render(request, "videos/register.html")

@api_view(["POST"])
def register_api(request):
    username = request.data.get("username", "").strip()
    email = request.data.get("email", "").strip().lower()
    password = request.data.get("password", "")
    password_confirm = request.data.get("password_confirm", "")

    if not username or not email or not password or not password_confirm:
        return Response(
            {"error": "All fields are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError

    try:
        validate_email(email)
    except ValidationError:
        return Response(
            {"error": "Please enter a valid email address."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(email__iexact=email).exists():
        return Response(
            {"error": "This email is already registered."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if password != password_confirm:
        return Response(
            {"error": "Passwords do not match."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(password) < 8:
        return Response(
            {"error": "Password must be at least 8 characters."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "Username already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )

    return Response(
        {
            "message": "Registration successful.",
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

    email = request.data.get("email", "").strip().lower()

    if not email:
        return Response(
            {"error": "Email is required."},
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
            f"Hello {user.username},\n\n"
            "We received a request to reset your password.\n\n"
            f"Open this link to choose a new password:\n{reset_link}\n\n"
            "If you did not request this, you can ignore this email."
        )

        print("DEBUG RESET LINK:", reset_link)

        send_mail(
            subject="VideoPlatform - Password Reset",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

    return Response(
        {
            "message": (
                "If an account is associated with this email, "
                "you will receive password reset instructions."
            )
        },
        status=status.HTTP_200_OK
    )

@api_view(["POST"])
def password_reset_confirm_api(request):

    uid = request.data.get("uid", "")
    token = request.data.get("token", "")
    new_password = request.data.get("new_password", "")
    password_confirm = request.data.get("password_confirm", "")

    if not all([uid, token, new_password, password_confirm]):
        return Response(
            {"error": "All fields are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if new_password != password_confirm:
        return Response(
            {"error": "Passwords do not match."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(new_password) < 8:
        return Response(
            {"error": "Password must be at least 8 characters."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user_id = urlsafe_base64_decode(uid).decode()
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response(
            {"error": "Invalid or expired reset link."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not default_token_generator.check_token(user, token):
        return Response(
            {"error": "Invalid or expired reset link."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    return Response(
        {"message": "Password has been reset successfully."},
        status=status.HTTP_200_OK
    )

def login(request):

    if request.method=="POST":

        username=request.POST.get("username","").strip()
        password=request.POST.get("password","")

        if not username or not password:

            return render(
                request,
                "videos/login.html",
                {
                    "error":"Username and password are required."
                }
            )

        user=authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:

            auth_login(request,user)

            return redirect("home")

        return render(
            request,
            "videos/login.html",
            {
                "error":"Invalid username or password."
            }
        )

    return render(
        request,
        "videos/login.html"
    )

@api_view(["POST"])
def login_api(request):

    username=request.data.get("username", "").strip()
    password=request.data.get("password", "")

    if not username or not password:
        return Response(
            {
                "error": "Username and password are required."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    user=authenticate(
        request,
        username=username,
        password=password
    )

    if user is None:
        return Response(
            {
                "error": "Invalid username or password."
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    refresh=RefreshToken.for_user(user)

    return Response(
        {
            "message":"Login successful",
            "username":user.username,
            "access":str(refresh.access_token),
            "refresh":str(refresh),
        },
        status=status.HTTP_200_OK
    )

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

    channel = get_object_or_404(
        User,
        id=user_id
    )

    if request.user == channel:

        return Response(
            {
                "error": "You cannot subscribe to yourself."
            },
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
        videos = videos.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search)
        )

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

@api_view(["GET", "POST"])
def comments(request, video_id):

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
                {"error": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        text = request.data.get("text", "").strip()

        if not text:

            return Response(
                {"error": "Comment text is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(text) > 1000:

            return Response(
                {
                    "error":
                    "Comment must be 1000 characters or less."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        parent = None
        parent_id = request.data.get("parent_comment_id")

        if parent_id not in (None, ""):

            try:
                parent_id = int(parent_id)
            except (TypeError, ValueError):

                return Response(
                    {"error": "Invalid parent comment ID."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            parent = get_object_or_404(
                Comment,
                id=parent_id,
                video=video
            )

            if parent.is_removed:
                return Response(
                    {"error": "You cannot reply to a removed comment."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        comment = Comment.objects.create(
            user=request.user,
            video=video,
            text=text,
            parent=parent
        )

        # Notify the video owner about a new top-level comment.
        if parent is None and video.user_id != request.user.id:
            notify_comment_interaction(
                recipient=video.user,
                sender=request.user,
                video=video,
                comment=comment,
                message=(
                    f"{request.user.username} commented on your video: "
                    f"{text[:180]}"
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
                message=(
                    f"{request.user.username} replied to your comment: "
                    f"{text[:180]}"
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
                message=(
                    f"{request.user.username} replied to a comment "
                    f"on your video: {text[:180]}"
                ),
                notification_type=Notification.NotificationType.COMMENT_REPLY
            )

        return Response(
            {
                "message": "Comment added successfully",
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
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": "This comment was removed for violating community guidelines."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if comment.user_id != request.user.id:
        return Response(
            {"error": "You can only edit your own comments."},
            status=status.HTTP_403_FORBIDDEN
        )

    text = request.data.get("text", "").strip()

    if not text:
        return Response(
            {"error": "Comment text is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(text) > 1000:
        return Response(
            {"error": "Comment must be 1000 characters or less."},
            status=status.HTTP_400_BAD_REQUEST
        )

    comment.text = text
    comment.save(update_fields=["text"])

    return Response({
        "message": "Comment updated successfully.",
        "comment": {
            "id": comment.id,
            "text": comment.text,
            "parent_comment_id": comment.parent_id,
        }
    }, status=status.HTTP_200_OK)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_comment_api(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.user_id != request.user.id:
        return Response(
            {"error": "You can only delete your own comments."},
            status=status.HTTP_403_FORBIDDEN
        )

    comment.delete()

    return Response(
        {"message": "Comment deleted successfully."},
        status=status.HTTP_200_OK
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def like_comment_api(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": "This comment was removed for violating community guidelines."},
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
                message=f"{request.user.username} liked your comment.",
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
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": "This comment was removed for violating community guidelines."},
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
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": "This comment was removed for violating community guidelines."},
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
    comment = get_object_or_404(Comment, id=comment_id)

    if comment.is_removed:
        return Response(
            {"error": "This comment was removed for violating community guidelines."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Users cannot report their own comments.
    if comment.user_id == request.user.id:
        return Response(
            {"error": "You cannot report your own comment."},
            status=status.HTTP_400_BAD_REQUEST
        )

    reason = request.data.get("reason", "").strip()
    details = request.data.get("details", "").strip()

    valid_reasons = [
        choice[0] for choice in CommentReport.Reason.choices
    ]

    if reason not in valid_reasons:
        return Response(
            {"error": "Please select a valid report reason."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(details) > 500:
        return Response(
            {"error": "Details must be 500 characters or less."},
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
            {"error": "You have already reported this comment."},
            status=status.HTTP_409_CONFLICT
        )

    return Response(
        {
            "message": "Comment reported successfully.",
            "report_id": report.id,
            "status": report.status,
        },
        status=status.HTTP_201_CREATED
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

@login_required
def dashboard(request):

    videos=Video.objects.filter(
        user=request.user
    ).order_by("-created_at")

    return render(
        request,
        "videos/dashboard.html",
        {
            "videos":videos
        }
    )

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

@login_required
def edit_profile(request):

    profile, created=Profile.objects.get_or_create(
        user=request.user
    )

    if request.method=="POST":

        profile_image=request.FILES.get("profile_image")

        bio=request.POST.get("bio")

        if profile_image:
            profile.profile_image=profile_image

        profile.bio=bio

        profile.save()

        return redirect(
            "user_profile",
            user_id=request.user.id
        )

    return render(
        request,
        "videos/edit_profile.html",
        {
            "profile": profile
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

    if "profile_image" in request.FILES:
        profile.profile_image = request.FILES["profile_image"]

    profile.save()

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

    new_username = request.data.get(
        "username", ""
    ).strip()

    if not new_username:
        return Response(
            {"error": "Username cannot be empty."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(
        username=new_username
    ).exclude(id=request.user.id).exists():
        return Response(
            {"error": "Username already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )

    request.user.username = new_username
    request.user.save(update_fields=["username"])

    return Response({
        "message": "Username updated successfully.",
        "username": request.user.username
    })

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def change_password_api(request):

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
            {"error": "All fields are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not user.check_password(current_password):
        return Response(
            {"error": "Current password is incorrect."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if new_password != password_confirm:
        return Response(
            {"error": "New passwords do not match."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(new_password) < 8:
        return Response(
            {"error": "Password must be at least 8 characters."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])

    return Response({
        "message": "Password updated successfully. Please log in again."
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

@login_required
def upload_video(request):

    if request.method=="POST":

        title=request.POST.get("title")
        description=request.POST.get("description")
        video_file=request.FILES.get("video_file")
        thumbnail=request.FILES.get("thumbnail")

        if not title:
            return render(
                request,
                "videos/upload_video.html",
                {
                    "error":"Title is required."
                }
            )

        if len(description)>5000:

            return render(
                request,
                "videos/edit_video.html",
                {
                    "error":"Description must be 5000 characters or less."
                }
            )

        error=validate_video_file(video_file)

        if error:

            return render(
                request,
                "videos/upload_video.html",
                {
                    "error":error
                }
            )

        error=validate_thumbnail_file(thumbnail)

        if error:

            return render(
                request,
                "videos/upload_video.html",
                {
                    "error":error
                }
            )

        video=Video.objects.create(
            user=request.user,
            title=title,
            description=description,
            video_file=video_file,
            thumbnail=thumbnail
        )

        notify_subscribers_new_video(video)

        return redirect("home")

    return render(
        request,
        "videos/upload_video.html"
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

@login_required
def edit_video(request,video_id):

    video=get_object_or_404(
        Video,
        id=video_id,
        user=request.user
    )

    if request.method=="POST":

        title=request.POST.get("title","").strip()
        description=request.POST.get("description")
        video_file=request.FILES.get("video_file")
        thumbnail=request.FILES.get("thumbnail")

        if not title:

            return render(
                request,
                "videos/edit_video.html",
                {
                    "video":video,
                    "error":"Title is required."
                }
            )

        if len(description)>5000:

            return render(
                request,
                "videos/edit_video.html",
                {
                    "video":video,
                    "error":"Description must be 5000 characters or less."
                }
            )

        video.title=title
        video.description=description

        if video_file:

            error=validate_video_file(video_file)

            if error:

                return render(
                    request,
                    "videos/edit_video.html",
                    {
                        "video":video,
                        "error":error
                    }
                )

        if thumbnail:

            error=validate_thumbnail_file(thumbnail)

            if error:

                return render(
                    request,
                    "videos/edit_video.html",
                    {
                        "video":video,
                        "error":error
                    }
                )

        if video_file:
            video.video_file=video_file

        if thumbnail:
            video.thumbnail=thumbnail

        video.save()

        return redirect("dashboard")

    return render(
        request,
        "videos/edit_video.html",
        {
            "video":video
        }
    )

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

    if title is not None:
        title = title.strip()

        if not title:
            return Response(
                {"error": "Title cannot be empty."},
                status=status.HTTP_400_BAD_REQUEST
            )

        video.title = title

    if description is not None:
        video.description = description.strip()

    if category_id is not None:
        category = get_object_or_404(
            Category,
            id=category_id
        )

        video.category = category

    if request.FILES.get("thumbnail"):
        video.thumbnail = request.FILES["thumbnail"]

    if request.FILES.get("video_file"):
        video.video_file = request.FILES["video_file"]

    video.save()

    return Response({
        "message": "Video updated successfully."
    })

@login_required
def delete_video(request,video_id):

    video=get_object_or_404(
        Video,
        id=video_id,
        user=request.user
    )

    if request.method=="POST":

        video.delete()

        return redirect("dashboard")

    return render(
        request,
        "videos/delete_video.html",
        {
            "video":video
        }
    )

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_video_api(request, video_id):

    video = get_object_or_404(
        Video,
        id=video_id,
        user=request.user
    )

    video.delete()

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
    user = request.user

    # Require password confirmation before irreversible deletion.
    password = request.data.get("password", "")

    if not password:
        return Response(
            {"error": "Password is required to delete your account."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not user.check_password(password):
        return Response(
            {"error": "Incorrect password."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    files_to_delete = []

    # Collect the user's video files and thumbnails.
    videos = Video.objects.filter(user=user).only(
        "video_file", "thumbnail"
    )

    for video in videos:
        if video.video_file:
            files_to_delete.append(video.video_file.name)

        if video.thumbnail:
            files_to_delete.append(video.thumbnail.name)

    # Collect the profile image, if one exists.
    profile = getattr(user, "profile", None)

    if profile and profile.profile_image:
        files_to_delete.append(profile.profile_image.name)

    def delete_media_files():
        for file_name in files_to_delete:
            try:
                default_storage.delete(file_name)
            except Exception:
                logger.exception(
                    "Failed to delete media file: %s", file_name
                )

    # Delete the database records first. Remove media only after commit.
    with transaction.atomic():
        user.delete()
        transaction.on_commit(delete_media_files)

    return Response(
        {"message": "Your account has been deleted successfully."},
        status=status.HTTP_200_OK,
    )
