#basic libraries
from django.urls import path

#import 
from im.views.category.views import categoryList, categoryCreate,categoryEdit,categoryDelete
from im.views.product.views import productList, productCreate,productEdit,productDelete
from im.views.audit_views import (
    audit_list, audit_start, audit_select_products, audit_enter_counts,
    audit_review, audit_apply_adjustments, audit_summary, audit_delete, audit_reports,
    audit_product_search
)
from im.views.import_products import import_products_csv_view
from im.views.despiece_views import despiece_list, despiece_process
from im.views.alarm_views import alarm_list, alarm_skip, alarm_skip_all, alarm_config, alarm_adjust, alarm_delete


app_name='im'
urlpatterns=[
        path('category/list',categoryList,name='categoryList'),
        path('category/create',categoryCreate,name='categoryCreate'),
        path('category/edit/<int:pk>/',categoryEdit, name='categoryEdit'),
        path('category/delete/<int:pk>/',categoryDelete,name='categoryDelete'),

        path('product/list',productList,name='productList'),
        path('product/create',productCreate,name='productCreate'),
        path('product/edit/<int:pk>/',productEdit, name='productEdit'),
        path('product/delete/<int:pk>/',productDelete,name='productDelete'),
        path('product/import-csv/', import_products_csv_view, name='import_products_csv'),

        # Audit URLs
        path('audit/', audit_list, name='audit_list'),
        path('audit/start/', audit_start, name='audit_start'),
        path('audit/reports/', audit_reports, name='audit_reports'),
        path('audit/<int:audit_id>/select/', audit_select_products, name='audit_select_products'),
        path('audit/<int:audit_id>/count/', audit_enter_counts, name='audit_enter_counts'),
        path('audit/<int:audit_id>/review/', audit_review, name='audit_review'),
        path('audit/<int:audit_id>/apply/', audit_apply_adjustments, name='audit_apply_adjustments'),
        path('audit/<int:audit_id>/summary/', audit_summary, name='audit_summary'),
        path('audit/<int:audit_id>/delete/', audit_delete, name='audit_delete'),
        path('audit/product-search/', audit_product_search, name='audit_product_search'),

        # Despiece URLs
        path('product/despiece/', despiece_list, name='despiece_list'),
        path('product/despiece/<int:pk>/process/', despiece_process, name='despiece_process'),

        # Alarm URLs
        path('alarms/', alarm_list, name='alarm_list'),
        path('alarms/skip/<int:alarm_id>/', alarm_skip, name='alarm_skip'),
        path('alarms/skip-all/', alarm_skip_all, name='alarm_skip_all'),
        path('alarms/config/', alarm_config, name='alarm_config'),
        path('alarms/adjust/<int:alarm_id>/', alarm_adjust, name='alarm_adjust'),
        path('alarms/delete/<int:alarm_id>/', alarm_delete, name='alarm_delete'),
        ]
