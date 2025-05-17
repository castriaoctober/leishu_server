from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search, name='search'),
    path('advanced_search/', views.advanced_search, name='advanced_search'),
    path('basic_search/', views.basic_search, name='basic_search'),
    path('search_result/', views.search_results, name='search_result'),
    path('similar_search_milvus/', views.similar_search_milvus, name='similar_search_milvus'),
    path('basic/', views.basic_search, name='basic_search'),
    path('advanced/', views.advanced_search, name='advanced_search'),
    path('similar/', views.similar_search_milvus, name='similar_search'),
    path('get_compare_texts/', views.get_compare_texts, name='get_compare_texts'),
]