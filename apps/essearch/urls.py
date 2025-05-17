from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search, name='search'),
    path('create_index/', views.create_es_index, name='create_es_index'),
    path('sync_data/', views.sync_data, name='sync_data'),
    path('sync_incremental_data/', views.sync_incremental_data, name='sync_incremental_data'),
    path('variant_search/', views.api_variant_search, name='variant_search'),
] 