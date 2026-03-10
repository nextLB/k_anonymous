from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()


class SignUpForm(forms.ModelForm):
    password1 = forms.CharField(label="密码", widget=forms.PasswordInput)
    password2 = forms.CharField(label="确认密码", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["username", "email"]
        labels = {"username": "用户名", "email": "邮箱（用于验证/找回密码）"}

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise ValidationError("邮箱不能为空")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("该邮箱已被注册")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "两次输入的密码不一致")
        if p1:
            validate_password(p1, user=None)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    identifier = forms.CharField(label="用户名或邮箱", required=True)
    password = forms.CharField(label="密码", widget=forms.PasswordInput, required=True)

    def clean(self):
        cleaned = super().clean()
        ident = (cleaned.get("identifier") or "").strip()
        pwd = cleaned.get("password") or ""
        if not ident or not pwd:
            return cleaned

        user = authenticate(username=ident, password=pwd)
        if user is None:
            # 尝试邮箱登录：把邮箱映射到用户名再认证
            try:
                u = User.objects.get(email__iexact=ident)
            except User.DoesNotExist:
                u = None
            if u is not None:
                user = authenticate(username=u.username, password=pwd)

        if user is None:
            raise ValidationError("用户名/邮箱或密码错误")

        cleaned["user"] = user
        return cleaned

