from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AnonymousUser
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, SignUpForm
from .models import UserProfile
from .tokens import make_email_verification_token, parse_email_verification_token
from django.contrib.auth import get_user_model

User = get_user_model()


def _site_url(request: HttpRequest) -> str:
    # 优先使用配置的 SITE_URL，避免反向代理下 host 错乱
    conf = getattr(settings, "SITE_URL", "")
    if conf:
        return conf.rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


def _send_verification_email(request: HttpRequest, user) -> None:
    token = make_email_verification_token(user_id=user.id, email=user.email)
    url = f"{_site_url(request)}/accounts/verify-email/{token}/"
    subject = "请验证你的邮箱（校园步行轨迹 K-匿名系统）"
    body = f"你好，{user.username}：\n\n请点击下面链接完成邮箱验证（链接有效期有限）：\n{url}\n\n如果不是你本人操作，请忽略此邮件。"
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


@require_http_methods(["GET", "POST"])
def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("/")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            # profile 由 signal 创建；保险起见 get_or_create
            UserProfile.objects.get_or_create(user=user)
            _send_verification_email(request, user)
            messages.success(request, "注册成功。验证邮件已发送（开发环境会打印在控制台）。")
            return redirect("/accounts/login/")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("/")
    next_url = request.GET.get("next") or request.POST.get("next") or "/"
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data["user"]
            login(request, user)
            messages.success(request, "登录成功")
            return redirect(next_url)
    else:
        form = LoginForm()
    return render(request, "accounts/login2.html", {"form": form, "next": next_url})


@login_required
@require_http_methods(["GET"])
def profile(request: HttpRequest) -> HttpResponse:
    prof, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(
        request,
        "accounts/profile.html",
        {
            "profile": prof,
            "require_verification": bool(getattr(settings, "REQUIRE_EMAIL_VERIFICATION", False)),
        },
    )


@login_required
@require_http_methods(["POST"])
def resend_verification(request: HttpRequest) -> HttpResponse:
    prof, _ = UserProfile.objects.get_or_create(user=request.user)
    if prof.email_verified:
        messages.info(request, "你的邮箱已验证，无需重复发送。")
        return redirect("/accounts/profile/")
    if not request.user.email:
        messages.error(request, "请先在管理员中为该用户补充邮箱。")
        return redirect("/accounts/profile/")
    _send_verification_email(request, request.user)
    messages.success(request, "验证邮件已重新发送（开发环境会打印在控制台）。")
    return redirect("/accounts/profile/")


@require_http_methods(["GET"])
def verify_email(request: HttpRequest, token: str) -> HttpResponse:
    try:
        payload = parse_email_verification_token(token)
        uid = int(payload["uid"])
        email = str(payload["email"]).strip().lower()
    except Exception:
        messages.error(request, "验证链接无效或已过期，请重新发送验证邮件。")
        return redirect("/accounts/login/")

    user = get_object_or_404(User, id=uid)
    if (user.email or "").strip().lower() != email:
        messages.error(request, "邮箱不匹配，验证失败。")
        return redirect("/accounts/login/")

    prof, _ = UserProfile.objects.get_or_create(user=user)
    prof.email_verified = True
    prof.email_verified_at = timezone.now()
    prof.save(update_fields=["email_verified", "email_verified_at"])
    messages.success(request, "邮箱验证成功。")
    return render(request, "accounts/verify_done.html", {"username": user.username})

