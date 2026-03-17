from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from .models import UserProfile


class EmailVerifiedRequiredMiddleware:
    """
    可选的“邮箱必须已验证才能访问核心功能”中间件。
    默认不强制；如需强制，在 settings.py 设置 REQUIRE_EMAIL_VERIFICATION=True。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        require = bool(getattr(settings, "REQUIRE_EMAIL_VERIFICATION", False))
        if require and getattr(request, "user", None) and request.user.is_authenticated:
            path = request.path or ""
            allow_prefixes = (
                "/accounts/",
                "/admin/",
                "/static/",
            )
            if not path.startswith(allow_prefixes):
                prof, _ = UserProfile.objects.get_or_create(user=request.user)
                if not prof.email_verified:
                    messages.warning(request, "请先完成邮箱验证后再使用系统核心功能。")
                    return redirect("/accounts/profile/")

        return self.get_response(request)

