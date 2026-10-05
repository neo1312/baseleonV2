from django.urls import path
from pos import views

app_name = 'pos'

urlpatterns = [
    path('', views.pos_landing, name='landing'),
    path('desktop/', views.pos_index, name='index'),
    path('touch/', views.pos_index_touch, name='index_touch'),
    path('search/', views.search_products, name='search'),
    path('search-index/', views.search_index, name='search_index'),
    path('search-stock/', views.search_stock, name='search_stock'),
    path('product/', views.get_product, name='get_product'),
    path('stock/', views.get_product_stock, name='get_stock'),
    path('validate-stock/', views.validate_stock, name='validate_stock'),
    path('debug-stock/', views.debug_stock, name='debug_stock'),
    path('complete-sale/', views.complete_sale, name='complete_sale'),
    path('get-sale-for-return/<int:sale_id>/', views.get_sale_for_return, name='get_sale_for_return'),
    path('cart/save/', views.cart_save, name='cart_save'),
    path('cart/get/', views.cart_get, name='cart_get'),
    path('customer-display/', views.customer_display, name='customer_display'),
    path('checkout/save/', views.checkout_save, name='checkout_save'),
    path('checkout/clear/', views.checkout_clear, name='checkout_clear'),
    path('reset-display/', views.reset_display, name='reset_display'),
    path('scan/', views.scan_product, name='scan'),
    path('scanner-push/', views.scanner_push, name='scanner_push'),
    path('scanner-poll/', views.scanner_poll, name='scanner_poll'),
    path('print-jobs/', views.create_print_job, name='create_print_job'),
    path('print-jobs/pending/', views.pending_print_jobs, name='pending_print_jobs'),
    path('print-jobs/ping/', views.print_ping, name='print_ping'),
    path('print-jobs/<int:job_id>/bytes/', views.print_job_bytes, name='print_job_bytes'),
    path('print-jobs/<int:job_id>/ack/', views.ack_print_job, name='ack_print_job'),
    path('print-jobs/<int:job_id>/fail/', views.fail_print_job, name='fail_print_job'),
    path('label/', views.label_page, name='label'),
    path('label-pdf/', views.label_pdf, name='label_pdf'),
    path('ticket/', views.ticket_page, name='ticket'),
    path('download-apk/', views.download_apk, name='download_apk'),
]

