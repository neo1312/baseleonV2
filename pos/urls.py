from django.urls import path
from pos import views

app_name = 'pos'

urlpatterns = [
    path('', views.pos_index, name='index'),
    path('search/', views.search_products, name='search'),
    path('product/', views.get_product, name='get_product'),
    path('stock/', views.get_product_stock, name='get_stock'),
    path('validate-stock/', views.validate_stock, name='validate_stock'),
    path('debug-stock/', views.debug_stock, name='debug_stock'),
    path('complete-sale/', views.complete_sale, name='complete_sale'),
]

