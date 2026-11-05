"""回归测试使用独立 MySQL 库，保留真实行锁语义。"""
import os
from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403

DEBUG = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
test_name = os.environ.get('DB_TEST_NAME', 'test_shetuan_regression')
if not test_name.startswith('test_') or test_name == DATABASES['default']['NAME']:  # noqa: F405
    raise ImproperlyConfigured('测试库必须以 test_ 开头，且不能与业务数据库同名。')
DATABASES['default']['TEST'] = {'NAME': test_name}  # noqa: F405
