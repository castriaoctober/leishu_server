from django.urls import path
from . import views

urlpatterns = [
    path('sign_in/', views.sign_in, name='sign_in'),
    path('sign_up/', views.sign_up, name='sign_up'),
    # path('sign_out/', views.sign_out, name='sign_out'),
    path('forgot_password/', views.forgot_password, name='forgot_password'),
    path('delete_account/', views.delete_account, name='delete_account'),

    path('user_dashboard/', views.user_dashboard, name='user_dashboard'),
    # path('admin_dashboard', views.admin_dashboard, name='admin_dashboard'),
    # path('profile/', views.profile, name='profile'),
    path('collections/', views.collections, name='collections'),
    path('bookmarks/', views.bookmarks, name='bookmarks'),
    path('history/', views.history, name='history'),
    # path('comments/', views.comments, name='comments')
    path('collections/check/', views.check_collection, name='check_collection'),
]