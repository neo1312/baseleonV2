from django.urls import path
from pos import views

app_name = 'pos'

urlpatterns = [
    path('', views.pos_index, name='index'),
    path('touch/', views.pos_index_touch, name='index_touch'),
    path('search/', views.search_products, name='search'),
    path('product/', views.get_product, name='get_product'),
    path('stock/', views.get_product_stock, name='get_stock'),
    path('validate-stock/', views.validate_stock, name='validate_stock'),
    path('debug-stock/', views.debug_stock, name='debug_stock'),
    path('complete-sale/', views.complete_sale, name='complete_sale'),
    path('cart/save/', views.cart_save, name='cart_save'),
    path('cart/get/', views.cart_get, name='cart_get'),
    path('customer-display/', views.customer_display, name='customer_display'),
    path('checkout/save/', views.checkout_save, name='checkout_save'),
    path('checkout/clear/', views.checkout_clear, name='checkout_clear'),
    path('reset-display/', views.reset_display, name='reset_display'),
    path('scan/', views.scan_product, name='scan'),
]

