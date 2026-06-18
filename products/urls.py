from django.urls import path
from . import views

urlpatterns = [
    path("list-uncached/", views.product_list_uncached),
    path("list-cached/", views.product_list_cached),

    path("<int:product_id>/detail-uncached/", views.product_detail_uncached),
    path("<int:product_id>/detail-cached/", views.product_detail_cached),

    path("popular-uncached/", views.popular_products_uncached),
    path("popular-cached/", views.popular_products_cached),

    path("cache-metrics/", views.cache_metrics_view),
    path("cache-metrics/reset/", views.reset_cache_metrics),
    path("cache-clear/", views.clear_product_cache),
]