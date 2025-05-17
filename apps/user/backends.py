from django.contrib.auth.backends import BaseBackend
from .models import User
from django.core.exceptions import MultipleObjectsReturned
from django.contrib.auth.hashers import check_password
from django.core.exceptions import PermissionDenied

class EmailOrUsernameModelBackend(BaseBackend):
    def authenticate(self, request, email_input=None, password=None, **kwargs):
        error = None
        user = None
        if email_input is None or password is None:
            # raise PermissionDenied("邮箱和密码不能为空")
            return None
        try:
            user = User.objects.get(email=email_input)
        except User.DoesNotExist:
            try:
                user = User.objects.get(user_name=email_input)
            except User.DoesNotExist:
                # raise PermissionDenied("用户不存在")
                error = "用户不存在"

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        elif not self.user_can_authenticate(user):
            # raise PermissionDenied("用户不存在")
            error = "用户不存在"
        else:
            # raise PermissionDenied("用户名或密码错误")
            error = "用户名或密码错误"

        if error is not None and hasattr(request, 'session'):
            request.session['login_error'] = error

        return user if error is None else None

    def user_can_authenticate(self, user):
        return user.is_active
