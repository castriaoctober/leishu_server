from django.urls import path
from . import views

urlpatterns = [
    path('docs/', views.DocListView.as_view(), name='doc-list'),
    path('stats/dynasty/', views.DynastyStatsView.as_view(), name='dynasty-stats'),
    path('category-tree/', views.CategoryTreeView.as_view(), name='category-tree'),
    path('docs/<int:doc_id>/', views.DocDetailView.as_view(), name='doc-detail'),
    path("docs/<int:doc_id>/titles/", views.TitleTreeView.as_view(), name="title-tree"),
    path("docs/<int:doc_id>/pages/", views.PageContentView.as_view(), name="page-content"),
    path("docs/<int:doc_id>/titles/<int:title_id>/texts/", views.TitleTextsView.as_view(), name="title-texts"),
    path('authors/<int:author_id>/', views.AuthorDetailView.as_view(), name='author-detail'),
    path('supplement-books/<int:doc_id>/', views.supplement_book_info, name='supplement_book_info'),
    path('reconstructions/<int:doc_id>/', views.get_reconstructed_texts, name='get_reconstructed_texts'),

    path('books/<int:doc_id>/origins/', views.get_book_origins, name='book-origins'),
    path('books/related/', views.get_related_books, name='related-books'),
]