"""
Django settings for leishu_server project.

Generated by 'django-admin startproject' using Django 5.1.6.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

from pathlib import Path
import os
import time


#-----------------------------#
# 自定义配置项，根据实际情况修改 #
#-----------------------------#

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default':
    {
        'ENGINE': 'django.db.backends.mysql',    # 数据库引擎
        'NAME': 'leishu_yongle', # 数据库名称
        'HOST': '127.0.0.1', # 数据库地址，本机 ip 地址 127.0.0.1
        'PORT': 3306, # 端口
        'USER': 'leishu',  # 数据库用户名
        'PASSWORD': 'Leishu(*&*112M!', # 数据库密码
    }
    }

# 数据库连接配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'leishu',
    'password': 'Leishu(*&*112M!',  # 请修改为你的MySQL密码
    'db': 'leishu_yongle',  # 使用新的数据库名
    'charset': 'utf8mb4'
}


# Elasticsearch连接配置
ES_NEEDS_AUTH = True

ES_CONFIG = {
    'hosts': [
        {
            'host': '120.26.247.52',  # 替换为 A 服务器的 IP 地址或域名
            'port': 9200,           # ES 默认端口
            'scheme': 'http'        # 或 'https' 如果配置了 SSL
        }
    ],
    # 如果需要认证
    'http_auth': ('leishu', 'Leishu(*&*112M!') if ES_NEEDS_AUTH else None,
    'timeout': 60,  # 增加超时时间，因为现在是远程连接
}



# 日志配置
LOGGER = "default"
WANDB_CONFIG = {
    "run_name": time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
    "log_interval": 10
}

ALLOWED_HOSTS = ['39.107.68.189', 'localhost', '127.0.0.1','111.205.230.232','116.172.93.147','123.57.204.18','120.26.247.52']

EMAIL_HOST_USER = '2300016618@stu.pku.edu.cn'   # 请替换为自己的邮箱

DOMAIN = '127.0.0.1:8000'

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-&=s#jb4+i-y^1c_iawz)=%su%!ll)rb_b+z$al17okjdu3y=2w'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

#--------------------#
# 以下配置轻易不要修改 #
#--------------------#


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',  # 后台管理模块
    'django.contrib.auth',  # 认证模块
    'django.contrib.contenttypes',  # 内容类型模块
    'django.contrib.sessions',  # 会话模块
    'django.contrib.messages',  # 消息模块
    'django.contrib.staticfiles',  # 静态文件模块
    'corsheaders',  # 添加corsheaders
    'apps.user',   # 防止与默认模块auth重名报错
    'apps.index',
    'apps.read',
    'apps.search',
    'apps.resource',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # 添加CORS中间件
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'leishu_server.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'leishu_server.wsgi.application'

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_USER_MODEL = 'user.User'


AUTHENTICATION_BACKENDS = [
    'apps.user.backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend'
]


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'zh-hans'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static/')

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS配置
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'

