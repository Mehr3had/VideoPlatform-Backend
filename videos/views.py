from django.shortcuts import render,get_object_or_404,redirect # type: ignore
from .models import Video,VideoReaction,Comment,Category,Subscription,Profile,VideoView
from django.contrib.auth.decorators import login_required # type: ignore
from django.contrib.auth.models import User # type: ignore
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate,login as auth_login # type: ignore
from django.contrib.auth import logout # type: ignore
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view,permission_classes
from django.db.models import Q
from django.core.paginator import Paginator
import os
from django.utils import timezone
from datetime import timedelta
from rest_framework.pagination import PageNumberPagination

class VideoPagination(PageNumberPagination):
    page_size = 6
    page_size_query_param = "page_size"
    max_page_size = 20

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

    video = get_object_or_404(
        Video,
        id=video_id
    )

    reaction_type=request.data.get("reaction","").lower().strip()

    if reaction_type not in [
        VideoReaction.LIKE,
        VideoReaction.DISLIKE
    ]:
        return Response(
            {
                "error":"Invalid reaction"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    reaction, created=VideoReaction.objects.get_or_create(
        user=request.user,
        video=video,
        defaults={
            "reaction_type":reaction_type
        }
    )

    if not created:

        if reaction.reaction_type==reaction_type:

            likes_count=VideoReaction.objects.filter(
                video=video,
                reaction_type=VideoReaction.LIKE
            ).count()

            dislikes_count=VideoReaction.objects.filter(
                video=video,
                reaction_type=VideoReaction.DISLIKE
            ).count()

            return Response({
                "message":f"You already {reaction_type}d this video",
                "reaction":reaction.reaction_type,
                "likes_count":likes_count,
                "dislikes_count":dislikes_count
            })

        reaction.reaction_type=reaction_type

        reaction.save(
            update_fields=["reaction_type"]
        )

        likes_count=VideoReaction.objects.filter(
            video=video,
            reaction_type=VideoReaction.LIKE
        ).count()

        dislikes_count=VideoReaction.objects.filter(
            video=video,
            reaction_type=VideoReaction.DISLIKE
        ).count()

        return Response({
            "message":"Reaction updated successfully",
            "reaction":reaction.reaction_type,
            "likes_count":likes_count,
            "dislikes_count":dislikes_count
        })

    likes_count=VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.LIKE
    ).count()

    dislikes_count=VideoReaction.objects.filter(
        video=video,
        reaction_type=VideoReaction.DISLIKE
    ).count()

    return Response({
        "message":"Reaction saved successfully",
        "reaction":reaction.reaction_type,
        "likes_count":likes_count,
        "dislikes_count":dislikes_count
    })

def register(request):

    if request.method=="POST":

        username=request.POST.get("username","").strip()
        password=request.POST.get("password","")

        if not username or not password:

            return render(
                request,
                "videos/register.html",
                {
                    "error":"Username and password are required."
                }
            )

        if len(username)<3:

            return render(
                request,
                "videos/register.html",
                {
                    "error":"Username must be at least 3 characters."
                }
            )

        if len(username)>30:

            return render(
                request,
                "videos/register.html",
                {
                    "error":"Username must be 30 characters or less."
                }
            )

        if len(password)<8:

            return render(
                request,
                "videos/register.html",
                {
                    "error":"Password must be at least 8 characters."
                }
            )

        if User.objects.filter(username=username).exists():

            return render(
                request,
                "videos/register.html",
                {
                    "error":"Username already exists."
                }
            )

        user=User.objects.create_user(
            username=username,
            password=password
        )

        Profile.objects.create(
            user=user
        )

        auth_login(request,user)

        return redirect("home")

    return render(
        request,
        "videos/register.html"
    )

@api_view(["POST"])
def register_api(request):

    username = request.data.get("username", "").strip()
    password = request.data.get("password", "")
    password_confirm = request.data.get("password_confirm", "")

    if not username or not password or not password_confirm:
        return Response(
            {
                "error": "All fields are required."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if password != password_confirm:
        return Response(
            {
                "error": "Passwords do not match."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(password) < 8:
        return Response(
            {
                "error": "Password must be at least 8 characters."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {
                "error": "Username already exists."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    user = User.objects.create_user(
        username=username,
        password=password
    )

    return Response(
        {
            "message": "Registration successful.",
            "id": user.id,
            "username": user.username,
        },
        status=status.HTTP_201_CREATED
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

@api_view(["GET","POST"])
def comments(request,video_id):

    video=get_object_or_404(
        Video,
        id=video_id
    )

    if request.method=="GET":

        comments=Comment.objects.filter(
            video=video
        ).order_by("-created_at")

        data=[]

        for comment in comments:

            data.append({
                "id":comment.id,
                "username":comment.user.username,
                "text":comment.text,
                "created_at":comment.created_at
            })

        return Response(data)

    if request.method=="POST":

        if not request.user.is_authenticated:

            return Response(
                {
                    "error":"Authentication required."
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        text=request.data.get("text","").strip()

        if not text:

            return Response(
                {
                    "error":"Comment text is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(text)>1000:

            return Response(

                {
                    "error":"Comment must be 1000 characters or less."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        comment=Comment.objects.create(
            user=request.user,
            video=video,
            text=text
        )

        return Response(
            {
                "message":"Comment added successfully",
                "comment": {
                    "id":comment.id,
                    "username":comment.user.username,
                    "text":comment.text,
                    "created_at":comment.created_at
                }
            },
            status=status.HTTP_201_CREATED
        )

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
        
        Video.objects.create(
            user=request.user,
            title=title,
            description=description,
            video_file=video_file,
            thumbnail=thumbnail
        )

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
