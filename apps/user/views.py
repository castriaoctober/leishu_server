# import email
import json
import bcrypt
from time import time, timezone
from copy import copy, deepcopy
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.core import serializers
from django.forms.models import model_to_dict
from django.db.models import Prefetch, F
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from .models import User, Bookmark, CollectedDoc, HistoryRecord
from ..read.models import Doc, Author, DALink, Title, FullText1, Page
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
import logging
logger = logging.getLogger(__name__)

SALT = bcrypt.gensalt(12)

# auth logy

@csrf_exempt  # 防止跨站请求伪造
@transaction.atomic  # 数据库操作失败时回滚
@require_http_methods(['POST'])
def sign_in(request):
    # 前端传回一个json数据，包含用户名/邮箱和密码，然后后端验证用户名/邮箱和密码是否正确，正确则返回一个token，前端存储token，每次请求都带上token，后端验证token，验证通过则允许访问，否则返回401
    data = json.loads(request.body)
    password_input = data.get('password', '')
    email_input = data.get('email', '')
    # print(email_input, password_input)
    password_input = password_input.encode('utf-8')
    try:
        user = authenticate(request, email_input=email_input, password=password_input)
    except Exception as e:
        print(e)
        return JsonResponse({'signed': False,'message': e}, status=401)

    if user is not None:
        # login(request, user)
        user_info = {
            'userId': user.user_id,
            'userName': user.user_name,
            'email': user.email,
            'lastLoginTime': user.last_log_in_time.strftime('%Y-%m-%d %H:%M:%S'),
            'createTime': user.create_time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        user.last_log_in_time = time()
        user.save()
        return JsonResponse({'signed': True, 'message': '登录成功',
                             'user_info': user_info}, status=200)
    else:
        # print(email_input, email_input, password_input)
        error = request.session.get('login_error', '')
        if 'login_error' in request.session:
            del request.session['login_error']


        return JsonResponse({'signed': False, 'message': error}, status=401)

@csrf_exempt
@transaction.atomic
def sign_up(request):
    # 前端传回一个json数据，包含用户名/邮箱和密码，然后后端验证用户名/邮箱是否已存在，不存在则创建用户，然后返回一个token，前端存储token，每次请求都带上token，后端验证token，验证通过则允许访问，否则返回401
    username = request.POST.get('username', '')
    email = request.POST.get('email', '')
    password = request.POST.get('password', '')
    password2 = request.POST.get('password2', '')
    if password != password2:
        return JsonResponse({'message': '两次密码输入不一致'}, status=400)
    if User.objects.filter(user_name=username).exists():
        return JsonResponse({'message': '用户名已存在'}, status=400)
    elif User.objects.filter(email=email).exists():
        return JsonResponse({'message': '此邮箱已注册'}, status=400)
    encoded_password = password.encode('utf-8')
    # 参看定义Users类的create_user方法, 会自动hash
    # hashed_password = bcrypt.hashpw(hashed_password, SALT)
    user = User.objects.create_user(
        user_name=username,
        email=email,
        password=encoded_password
    )
    user.save()
    print("Received sign_up request")
    return JsonResponse({'success': True, 'message': '注册成功'})

def sign_out(request):
#     # 前端点击注销按钮，后端清除session，并返回首页
#     data = json.loads(request.body)
#     user_id = int(data.get('user_id', ''))
#     user = User.objects.filter(id=user_id).first()
#     if user is None:
#         return JsonResponse({'message': '用户不存在'}, status=400)
#     try:
#         # logout(request)
#         return JsonResponse({'signed_out': True,' message': '注销成功'}, status=200)
#     except Exception as e:
#         return JsonResponse({'signed_out': False,' message': e}, status=500)
    pass
#
def forgot_password(request):
    # 前端传回一个json数据，包含用户名/邮箱，然后后端发送邮件给用户，包含重置密码的链接，用户点击链接后，输入新密码，然后提交，后端验证密码是否正确，正确则修改密码，然后返回成功信息，否则返回失败信息
    to_email = request.POST.get('email', '')
    title = 'xxx.com重置密码'
    #  此处需要写一个回调函数，当用户点击重置密码链接时，会跳转到一个页面，然后将token和用户信息传递给后端，后端验证token，然后修改密码
    url = 'http://localhost:8000/reset_password/'
    message = '请点击下面的链接重置密码：{}'.format(url)
    from_email = settings.EMAIL_HOST_USER
    ret = send_mail(title, message, from_email, [to_email], fail_silently=True)
    if not ret:
        return JsonResponse({'message': '邮件发送失败'}, status=400)
    return JsonResponse({'message': '邮件发送成功'}, status=200)
#
def reset_password(request):
    return HttpResponse("Reset Password Page")
#
def delete_account(request):
    if request.method != 'POST':
        return JsonResponse({'message': '请求方式错误'}, status=400)

    data = json.loads(request.body)
    user_id = int(data.get('user_id', ''))
    user = User.objects.filter(user_id=user_id).first()
    try:
        # user.delete()
        user.is_active = False
        user.save()
    except User.DoesNotExist:
        return JsonResponse({'message': '用户不存在'}, status=400)
    return JsonResponse({'message': '删除成功'}, status=200)

# user dashboard
@csrf_exempt # 免除CSRF验证
@require_http_methods(['POST'])
def user_dashboard(request):
    """前端传回当前用户的id，后端返回该用户的基本信息、收藏、书签、历史记录"""
    # print(request.body)
    user_info = json.loads(request.body).get('user_info', {})
    user_id = user_info.get('userId', '')
    user = User.objects.filter(user_id=user_id).first()
    if user is None:
        return JsonResponse({'signed': False, 'message': '请先登录！'}, status=400)
    try:
        def get_user_items(user_id):
            """
            获取用户收藏、书签和历史记录（优化版）
            使用select_related/prefetch_related减少查询次数
            """
            # 预取关联的Doc数据
            doc_prefetch = Prefetch(
                'doc',
                queryset=Doc.objects.only('doc_id', 'doc_title')
            )

            # 一次查询获取所有收藏及相关文档
            collections = CollectedDoc.objects.filter(
                user_id=user_id
            ).select_related('doc').order_by('-create_time').values(
                'collect_id',
                'doc_id',
                'create_time',
                doc_title=F('doc__doc_title')
            )

            # 书签数据
            bookmarks = Bookmark.objects.filter(
                user_id=user_id
            ).select_related('doc').order_by('-create_time').values(
                'mark_id',
                'doc_id',
                'page_id',
                'create_time',
                'selection_data',
                'note',
                doc_title=F('doc__doc_title')
            )

            # 历史记录
            history = HistoryRecord.objects.filter(
                user_id=user_id
            ).select_related('doc').order_by('-browse_time').values(
                'history_id',
                'doc_id',
                'browse_time',
                doc_title=F('doc__doc_title')
            )

            return (
                list(collections),
                list(bookmarks),
                list(history)
            )

        # 获取数据
        collections, bookmarks, history = get_user_items(user_id)

        # 构建响应数据
        response_data = {
            'collections': collections,
            'bookmarks': bookmarks,
            'history': history,
            'status': 'success'
        }
        print(response_data)
        return JsonResponse(response_data)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        print(e)
        # raise e
        return JsonResponse({'error': str(e)}, status=500)

# def profile(request):
#     return HttpResponse("Profile Page")

@csrf_exempt # 免除CSRF验证
def collections(request):
    data = json.loads(request.body)
    user_id = int(data.get('user_id', ''))
    doc_id = int(data.get('doc_id', ''))
    action = data.get('action', '')
    if action == 'add':
        try:
            CollectedDoc.objects.get(user_id=user_id, doc_id=doc_id)
            return JsonResponse({'message': '收藏记录已存在'}, status=400)
        except CollectedDoc.DoesNotExist:
            try:
                tag = data.get('tag', '')
                c = CollectedDoc.objects.create(user_id=user_id, doc_id=doc_id, tag=tag)
                return JsonResponse({'message': '收藏成功'}, status=200)
            except Exception as e:
                return JsonResponse({'message': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'message': str(e)}, status=400)
    elif action == 'delete':
        try:
            CollectedDoc.objects.get(user_id=user_id, doc_id=doc_id).delete()
            return JsonResponse({'message': '取消收藏成功'}, status=200)
        except CollectedDoc.DoesNotExist:
            return JsonResponse({'message': '收藏记录不存在'}, status=400)
        except Exception as e:
            return JsonResponse({'message': str(e)}, status=400)
    else:
        return JsonResponse({'message': '请求方式错误'}, status=400)

@csrf_exempt # 免除CSRF验证
def bookmarks(request):
    data = json.loads(request.body)
    user_id = int(data.get('user_id', ''))
    doc_id = int(data.get('doc_id', ''))
    page_id = int(data.get('page_id', ''))
    selection_data = data.get('selection_data','')
    action = data.get('action', '')
    if action == 'add':
        if Bookmark.objects.filter(user_id=user_id, doc_id=doc_id,page_id=page_id,selection_data=selection_data).exists():
            return JsonResponse({'message': '书签记录已存在'}, status=400)

        note = data.get('note', '')
        tag = data.get('tag', '')
        

        try:
            mark = Bookmark.objects.create(user_id=user_id, doc_id=doc_id, page_id=page_id,
                                                note=note, tag=tag,selection_data=selection_data)
            mark.save()
            return JsonResponse({'message': '添加书签成功'}, status=200)
        except Exception as e:
            return JsonResponse({'message': str(e)}, status=400)
    elif action == 'delete':
        mark_id = int(data.get('mark_id', ''))
        try:
            Bookmark.objects.get(mark_id=mark_id).delete()
            return JsonResponse({'message': '删除成功'}, status=200)
        except Bookmark.DoesNotExist:
            return JsonResponse({'message': '书签记录不存在'}, status=400)
        except Exception as e:
            return JsonResponse({'message': str(e)}, status=400)
        
@csrf_exempt
def history(request):
    logger.info(f"收到请求: {request.method} {request.body}")
    
    if request.method != 'POST':
        logger.warning("非POST请求")
        return JsonResponse({'message': '仅支持POST请求'}, status=405)
    
    try:
        data = json.loads(request.body)
        logger.info(f"解析后的数据: {data}")
        
        user_id = int(data.get('user_id', ''))
        doc_id = int(data.get('doc_id', ''))
        logger.info(f"转换后的参数 - user_id: {user_id}, doc_id: {doc_id}")
        
    except (ValueError, TypeError) as e:
        logger.error(f"参数解析错误: {str(e)}")
        return JsonResponse({'message': f'参数错误: {str(e)}'}, status=400)
    
    try:
        from django.utils import timezone
        now_time = timezone.now()  # 使用Django的timezone获取当前时间
        
        record, created = HistoryRecord.objects.get_or_create(
            user_id=user_id, 
            doc_id=doc_id,
            defaults={'browse_time': now_time}
        )
        
        if not created:
            record.browse_time = now_time
            record.save()
            
        logger.info(f"记录{'创建' if created else '更新'}成功")
        return JsonResponse({
            'message': f'记录{"创建" if created else "更新"}成功',
            'created': created
        }, status=200)
            
    except Exception as e:
        logger.error(f"操作失败: {str(e)}")
        return JsonResponse({'message': str(e)}, status=400)
    
# 检查是否已经收藏文章
def check_collection(request):
    try:
        user_id = request.GET.get('user_id')
        doc_id = request.GET.get('doc_id')
        
        is_collected = CollectedDoc.objects.filter(
            user_id=user_id,
            doc_id=doc_id
        ).exists()
        
        return JsonResponse({'is_collected': is_collected})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# def comments(request):
#     return HttpResponse("Comments Page")


# admin dashboard

def admin_dashboard(request):
    return HttpResponse("Admin Dashboard Page")

def monitor(request):
    return HttpResponse("Monitor Page")




# # 在views.py中添加

# from django.http import JsonResponse
# from django.views.decorators.http import require_POST
# from .models import CollectedDoc

# @require_POST
# def add_collection(request):
#     try:
#         data = json.loads(request.body)
#         user_id = data.get('user_id')
#         doc_id = data.get('doc_id')
        
#         # 检查是否已收藏
#         if CollectedDoc.objects.filter(user_id=user_id, doc_id=doc_id).exists():
#             return JsonResponse({'success': False, 'message': '已收藏过该文献'})
            
#         CollectedDoc.objects.create(
#             user_id=user_id,
#             doc_id=doc_id
#         )
#         return JsonResponse({'success': True})
#     except Exception as e:
#         return JsonResponse({'success': False, 'message': str(e)})

# @require_POST
# def remove_collection(request):
#     try:
#         data = json.loads(request.body)
#         user_id = data.get('user_id')
#         doc_id = data.get('doc_id')
        
#         CollectedDoc.objects.filter(
#             user_id=user_id,
#             doc_id=doc_id
#         ).delete()
#         return JsonResponse({'success': True})
#     except Exception as e:
#         return JsonResponse({'success': False, 'message': str(e)})


