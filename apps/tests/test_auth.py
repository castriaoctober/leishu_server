# app/tests/test_auth.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

class LoginTests(TestCase):
    def setUp(self):
        """创建测试用户"""
        self.user = get_user_model().objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.login_url = reverse('sign_in')  # 替换为你的登录路由名

    def test_successful_login(self):
        """测试正确用户名密码登录"""
        response = self.client.post(
            self.login_url,
            {
                'username': 'testuser',
                'email': 'test@example.com',
                'password': 'testpass123'
            }
        )
        # 检查是否重定向到目标页面（假设登录后跳转到首页）
        self.assertRedirects(response, reverse('index'))
        # 检查用户是否已登录
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_invalid_password_login(self):
        """测试错误密码登录"""
        response = self.client.post(
            self.login_url,
            {
                'username': 'testuser',
                'email': 'test@example.com',
                'password': 'wrongpassword'
            }
        )
        # 检查返回状态码（表单错误时通常返回 200）
        self.assertEqual(response.status_code, 200)
        # 检查错误消息是否存在（根据你的模板实际提示内容调整）
        self.assertContains(response, 'Invalid username or password')
        # 检查用户未登录
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_nonexistent_user_login(self):
        """测试不存在的用户登录"""
        response = self.client.post(
            self.login_url,
            {
                'username': 'notexist',
                'email': 'notexist@example.com',
                'password': 'anypassword'
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid username or password')
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    # def test_login_template_used(self):
    #     """测试是否使用了正确的登录模板"""
    #     response = self.client.get(self.login_url)
    #     self.assertEqual(response.status_code, 200)
    #     self.assertTemplateUsed(response, 'registration/login.html')  # 替换为你的模板路径

    def test_login_session_creation(self):
        """测试登录后会话中是否有用户ID"""
        self.client.login(username='testuser', password='testpass123')
        session = self.client.session
        self.assertEqual(session['_auth_user_id'], str(self.user.pk))

    # def test_empty_form_submission(self):
    #     """测试空表单提交"""
    #     response = self.client.post(self.login_url, {})
    #     self.assertEqual(response.status_code, 200)
    #     self.assertFormError(response, 'form', 'username', 'This field is required.')
    #     self.assertFormError(response, 'form', 'password', 'This field is required.')

    def test_csrf_protection(self):
        """测试是否包含CSRF令牌"""
        response = self.client.get(self.login_url)
        self.assertContains(response, 'csrfmiddlewaretoken')

    # def test_redirect_after_login(self):
    #     """测试带next参数的登录重定向"""
    #     next_url = reverse('profile')
    #     response = self.client.post(
    #         f"{self.login_url}?next={next_url}",
    #         {'username': 'testuser', 'password': 'testpass123'}
    #     )
    #     self.assertRedirects(response, next_url)