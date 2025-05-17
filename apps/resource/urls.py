from django.urls import path
from .views import ResourceView

urlpatterns = [
    path('document/', ResourceView.as_view(), name='document'),
    path('author/', ResourceView.as_view(), name='author'),
    path('document_author/', ResourceView.as_view(), name='document_author'),
    path('title/', ResourceView.as_view(), name='title'),
    path('fulltext/', ResourceView.as_view(), name='fulltext'),
    path('page/', ResourceView.as_view(), name='page'),
] 