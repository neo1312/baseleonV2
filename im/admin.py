from django.contrib import admin
from im.models import Product, Category, Cost, Margin, Brand, InventoryUnit, ABCConfiguration, ProductABCMetrics, ForecastConfiguration, DemandForecast, ProductProvider, InventoryAudit, AuditItem, AdjustmentTransaction
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.db.models import Sum, F, DecimalField

class categoryResource(resources.ModelResource):
    class Meta:
        model=Category

class categoryAdmin(ImportExportModelAdmin,admin.ModelAdmin):
    search_fields=['name','id']
    list_display=('id','name')
    list_filter=('id',)
    resocurce_class = categoryResource

admin.site.register(Category,categoryAdmin)

class productResource(resources.ModelResource):
    class Meta:
        model=Product
        fields = ('name','clave','barcode','costo','margen','margenMayoreo','margenGranel','active','sat','category','brand','stockMax','stockMin','minimo','unidad','unidadEmpaque','granel','monedero_percentaje','provedor')
        skip_unchanged = True
        report_skipped = True
        import_id_fields = ()  # Don't use any field as ID lookup
    
    def before_create_instance(self, data, row_number, **kwargs):
        """Let Django auto-generate the ID - don't try to set it"""
        # Remove id if it's in data
        data.pop('id', None)
        return data

class ProductProviderInline(admin.TabularInline):
    model = ProductProvider
    extra = 1
    fields = ('provider', 'pv1', 'provider_cost', 'date_created', 'last_updated')
    readonly_fields = ('date_created', 'last_updated')
    raw_id_fields = ('provider',)

class productAdmin(ImportExportModelAdmin,admin.ModelAdmin):
    search_fields=['name','category__name','brand__name','id','barcode','clave']
    list_display=('id','clave','full_name','get_stock_ready_to_sale','costo','priceLista','priceListaGranel','priceMayoreo','active','sat')
    list_filter=('active','brand','category','provedor')
    resocurce_class = productResource
    ordering=('id','last_updated')
    raw_id_fields=('provedor','brand','category')
    inlines = [ProductProviderInline]
    change_list_template = "admin/im/product/change_list.html"
    #list_per_page = 1000
    exclude = ('stock',)  # Exclude deprecated stock field from admin form

    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'clave', 'category', 'brand', 'barcode', 'sat', 'active')
        }),
        ('Inventory Settings', {
            'fields': ('minimo', 'stockMax', 'stockMin', 'unidad', 'unidadEmpaque', 'granel', 'inventory_no', 'display_stock')
        }),
        ('Cost', {
            'fields': ('costo',)
        }),
        ('Pricing - Regular', {
            'fields': ('pricing_mode', 'margen', 'precio_manual'),
            'description': 'Select "Usar Margen" to set margin and calculate price, or "Usar Precio Manual" to set price and calculate margin'
        }),
        ('Pricing - Mayoreo (Wholesale)', {
            'fields': ('mayoreo_pricing_mode', 'margenMayoreo', 'precio_mayoreo_manual'),
            'description': 'Select "Usar Margen" to set margin and calculate price, or "Usar Precio Manual" to set price and calculate margin'
        }),
        ('Pricing - Granel (Bulk)', {
            'fields': ('granel_pricing_mode', 'margenGranel', 'precio_granel_manual'),
            'description': 'Only active when "Granel" is enabled. Select "Usar Margen" to set margin and calculate price, or "Usar Precio Manual" to set price and calculate margin'
        }),
        ('Monedero', {
            'fields': ('monedero_percentaje',)
        }),
        ('System', {
            'fields': ('date_created', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('id', 'date_created', 'last_updated', 'display_stock')

    def get_fieldsets(self, request, obj=None):
        """Hide ID field when creating new product, show when editing"""
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:  # Creating new product
            fieldsets = list(fieldsets)
            fieldsets[0] = (fieldsets[0][0], {'fields': ('name', 'clave', 'category', 'brand', 'barcode', 'sat', 'active')})
        else:  # Editing existing product
            fieldsets = list(fieldsets)
            fieldsets[0] = (fieldsets[0][0], {'fields': ('id', 'name', 'clave', 'category', 'brand', 'barcode', 'sat', 'active')})
        return fieldsets

    def display_stock(self, obj):
        """Display stock_ready_to_sale as 'Stock' in the form"""
        return obj.stock_ready_to_sale
    display_stock.short_description = 'Stock'

    def get_stock_ready_to_sale(self, obj):
        """Display stock_ready_to_sale as a read-only field"""
        return obj.stock_ready_to_sale
    get_stock_ready_to_sale.short_description = 'Available Stock'
    get_stock_ready_to_sale.admin_order_field = None  # Cannot order by property

    #Calculate total inventory value
    def changelist_view(self, request, extra_context=None):
        # Calculate total using Python since stock_ready_to_sale is a @property
        products = Product.objects.all()
        total = sum(float(p.costo) * p.stock_ready_to_sale for p in products)

        extra_context = extra_context or {}
        extra_context['total_inventory_value']=total
        extra_context['import_csv_url'] = '/im/product/import-csv/'
        return super().changelist_view(request, extra_context=extra_context)
    
    def delete_model(self, request, obj):
        """Override delete to show what will be deleted"""
        from django.contrib import messages
        from scm.models import PurchaseOrderItem
        from crm.models import saleItem, devolutionItem
        
        # Count orphaned references
        po_items = PurchaseOrderItem.objects.filter(product=obj).count()
        sale_items = saleItem.objects.filter(product=obj).count()
        dev_items = devolutionItem.objects.filter(product=obj).count()
        
        info = f"Product '{obj.name}' deleted. "
        orphans = []
        if po_items:
            orphans.append(f"{po_items} PO items")
        if sale_items:
            orphans.append(f"{sale_items} sales")
        if dev_items:
            orphans.append(f"{dev_items} devolutions")
        
        if orphans:
            info += f"Orphaned: {', '.join(orphans)}. These records remain with no product reference."
        
        # Delete ABC metrics if exists
        if hasattr(obj, 'abc_metrics'):
            try:
                obj.abc_metrics.delete()
                info += " ABC metrics deleted."
            except:
                pass
        
        # Delete forecast if exists
        if hasattr(obj, 'demand_forecast'):
            try:
                obj.demand_forecast.delete()
                info += " Forecast deleted."
            except:
                pass
        
        messages.success(request, info)
        super().delete_model(request, obj)

admin.site.register(Product,productAdmin)

class brandResource(resources.ModelResource):
    class Meta:
        model=Brand

class brandAdmin(ImportExportModelAdmin,admin.ModelAdmin):
    search_fields=['id','name']
    list_display=('id','name')
    list_filter=()
    resocurce_class = brandResource

admin.site.register(Brand,brandAdmin)


class ProductProviderResource(resources.ModelResource):
    class Meta:
        model = ProductProvider
        fields = ('product', 'provider', 'pv1', 'provider_cost')
        skip_unchanged = True
        report_skipped = True
        import_id_fields = ()  # Don't use any field as ID lookup
    
    def before_create_instance(self, data, row_number, **kwargs):
        """Let Django auto-generate the ID - don't try to set it"""
        # Remove id if it's in data
        data.pop('id', None)
        return data

class ProductProviderAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    search_fields = ['product__name', 'product__barcode', 'provider__name', 'pv1']
    list_display = ('id', 'product', 'provider', 'pv1', 'provider_cost', 'date_created')
    list_filter = ('provider', 'date_created', 'product__category')
    resource_class = ProductProviderResource
    ordering = ('-date_created',)
    readonly_fields = ('date_created', 'last_updated', 'id')
    raw_id_fields = ('product', 'provider')

admin.site.register(ProductProvider, ProductProviderAdmin)


class InventoryUnitAdmin(admin.ModelAdmin):
    search_fields=['tracking_id', 'product__name', 'product__barcode', 'purchase_order__po_number', 'purchase_order__provider__name']
    list_display=('tracking_id', 'product', 'get_po_number', 'get_provider_name', 'status', 'purchase_cost', 'received_cost', 'abc_classification', 'received_date')
    list_filter=('status', 'abc_classification', 'date_created', 'product')
    readonly_fields=('tracking_id', 'date_created', 'last_updated', 'purchase_item', 'sale_item')
    ordering=('-date_created',)
    
    def get_po_number(self, obj):
        """Display PO number if unit belongs to a purchase order"""
        if obj.purchase_order:
            return obj.purchase_order.po_number
        return ""
    get_po_number.short_description = 'PO #'
    get_po_number.admin_order_field = 'purchase_order__po_number'
    
    def get_provider_name(self, obj):
        """Display provider name if unit belongs to a purchase order"""
        if obj.purchase_order and obj.purchase_order.provider:
            return obj.purchase_order.provider.name
        return "-"
    get_provider_name.short_description = 'Provider'
    get_provider_name.admin_order_field = 'purchase_order__provider__name'
    
    fieldsets = (
        ('Identification', {
            'fields': ('tracking_id', 'product', 'purchase_item', 'sale_item')
        }),
        ('Status & Classification', {
            'fields': ('status', 'abc_classification')
        }),
        ('Costs', {
            'fields': ('purchase_cost', 'received_cost'),
            'description': 'Purchase cost is set when order is placed. Received cost is updated when order arrives (may differ if price changed).'
        }),
        ('Timeline', {
            'fields': ('ordered_date', 'received_date', 'ready_date', 'sold_date', 'retired_date')
        }),
        ('Metadata', {
            'fields': ('date_created', 'last_updated'),
            'classes': ('collapse',)
        }),
    )

admin.site.register(InventoryUnit, InventoryUnitAdmin)


class ABCConfigurationAdmin(admin.ModelAdmin):
    list_display=('time_period_days', 'pareto_a_threshold', 'pareto_b_threshold', 'auto_recalculate', 'last_recalculation')
    readonly_fields=('last_recalculation', 'date_created', 'last_updated')
    actions = ['recalculate_abc_now']
    
    fieldsets = (
        ('ABC Calculation Settings', {
            'fields': ('time_period_days', 'pareto_a_threshold', 'pareto_b_threshold')
        }),
        ('Auto-recalculation', {
            'fields': ('auto_recalculate',),
            'description': 'When enabled, ABC classifications are recalculated automatically after sales and devolutions'
        }),
        ('Metadata', {
            'fields': ('last_recalculation', 'date_created', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        return not ABCConfiguration.objects.exists()
    
    def recalculate_abc_now(self, request, queryset):
        """Admin action to manually trigger ABC recalculation"""
        from im.abc_calculation import recalculate_abc
        try:
            result = recalculate_abc()
            self.message_user(
                request,
                f'✓ ABC recalculation complete: {result["products"]} products, {result["units"]} units updated',
                level='success'
            )
        except Exception as e:
            self.message_user(
                request,
                f'✗ Error during ABC recalculation: {str(e)}',
                level='error'
            )
    
    recalculate_abc_now.short_description = "Recalculate ABC classifications now"

admin.site.register(ABCConfiguration, ABCConfigurationAdmin)


class ProductABCMetricsAdmin(admin.ModelAdmin):
    search_fields=['product__name', 'product__barcode']
    list_display=('product', 'abc_classification', 'last_30_days_units_sold', 'last_30_days_revenue', 'cumulative_revenue_percentage')
    list_filter=('abc_classification', 'last_updated')
    readonly_fields=('product', 'date_created', 'last_updated')
    ordering=('-abc_classification', '-last_30_days_revenue')
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(ProductABCMetrics, ProductABCMetricsAdmin)


class ForecastConfigurationAdmin(admin.ModelAdmin):
    list_display=('alpha', 'beta', 'lookback_period_days', 'forecast_horizon_days', 'auto_recalculate', 'last_recalculation')
    readonly_fields=('last_recalculation', 'date_created', 'last_updated')
    actions = ['recalculate_forecasts_now']
    
    fieldsets = (
        ('Exponential Smoothing Parameters', {
            'fields': ('alpha', 'beta'),
            'description': 'α (alpha): responsiveness to changes (0.1-0.5)<br/>β (beta): trend influence (0.01-0.2)'
        }),
        ('Forecast Settings', {
            'fields': ('lookback_period_days', 'forecast_horizon_days', 'include_seasonality')
        }),
        ('Inventory Optimization', {
            'fields': ('safety_stock_multiplier', 'supplier_lead_time_days')
        }),
        ('Auto-recalculation', {
            'fields': ('auto_recalculate',)
        }),
        ('Metadata', {
            'fields': ('last_recalculation', 'date_created', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        return not ForecastConfiguration.objects.exists()
    
    def recalculate_forecasts_now(self, request, queryset):
        """Admin action to manually trigger forecast recalculation"""
        from im.forecast_runner import recalculate_all_forecasts
        try:
            result = recalculate_all_forecasts()
            self.message_user(
                request,
                f'✓ Forecasts updated: {result["updated"]} products, {result["errors"]} errors',
                level='success'
            )
        except Exception as e:
            self.message_user(
                request,
                f'✗ Error during forecast recalculation: {str(e)}',
                level='error'
            )
    
    recalculate_forecasts_now.short_description = "Recalculate all demand forecasts now"

admin.site.register(ForecastConfiguration, ForecastConfigurationAdmin)


class DemandForecastAdmin(admin.ModelAdmin):
    search_fields=['product__name', 'product__barcode']
    list_display=('product', 'forecast_daily', 'forecast_30days', 'confidence_level', 'reorder_point', 'eoq', 'last_updated')
    list_filter=('confidence_level', 'last_updated')
    readonly_fields=('product', 'forecast_daily', 'forecast_30days', 'confidence_level', 'lower_bound', 'upper_bound', 'trend', 'mape', 'reorder_point', 'eoq', 'last_sales_data_count', 'date_created', 'last_updated')
    ordering=('-forecast_daily',)
    
    fieldsets = (
        ('Product', {
            'fields': ('product',)
        }),
        ('Forecast Values', {
            'fields': ('forecast_daily', 'forecast_30days', 'trend')
        }),
        ('Confidence & Bounds', {
            'fields': ('confidence_level', 'lower_bound', 'upper_bound', 'mape')
        }),
        ('Recommendations', {
            'fields': ('reorder_point', 'eoq')
        }),
        ('Metadata', {
            'fields': ('last_sales_data_count', 'date_created', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(DemandForecast, DemandForecastAdmin)


# ============================================================================
# INVENTORY AUDIT ADMIN
# ============================================================================

class AuditItemInline(admin.TabularInline):
    model = AuditItem
    extra = 0
    fields = ('product', 'system_count', 'physical_count', 'discrepancy', 'adjustment_reason', 'adjustment_status', 'notes')
    readonly_fields = ('discrepancy',)
    raw_id_fields = ('product',)


class InventoryAuditAdmin(admin.ModelAdmin):
    list_display = ('id', 'audit_date', 'get_audit_type_display', 'status', 'auditor', 'total_items_audited', 'total_discrepancies', 'total_adjustment_value')
    list_filter = ('status', 'audit_type', 'audit_date')
    search_fields = ('auditor', 'id')
    readonly_fields = ('id', 'total_items_audited', 'total_discrepancies', 'total_adjustment_value', 'created_at', 'started_at', 'completed_at')
    inlines = [AuditItemInline]
    ordering = ('-audit_date',)
    
    fieldsets = (
        ('Audit Info', {
            'fields': ('id', 'audit_date', 'audit_type', 'status')
        }),
        ('Auditor', {
            'fields': ('auditor', 'reviewed_by')
        }),
        ('Statistics', {
            'fields': ('total_items_audited', 'total_discrepancies', 'total_adjustment_value'),
            'description': 'Auto-calculated from audit items'
        }),
        ('Timeline', {
            'fields': ('created_at', 'started_at', 'completed_at')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    
    actions = ['mark_as_in_progress', 'mark_as_under_review', 'mark_as_completed']
    
    def mark_as_in_progress(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='in_progress', started_at=timezone.now())
        self.message_user(request, f'{updated} audit(s) marked as in progress.')
    mark_as_in_progress.short_description = 'Mark selected as In Progress'
    
    def mark_as_under_review(self, request, queryset):
        updated = queryset.update(status='under_review')
        self.message_user(request, f'{updated} audit(s) marked as under review.')
    mark_as_under_review.short_description = 'Mark selected as Under Review'
    
    def mark_as_completed(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='completed', completed_at=timezone.now())
        self.message_user(request, f'{updated} audit(s) marked as completed.')
    mark_as_completed.short_description = 'Mark selected as Completed'

admin.site.register(InventoryAudit, InventoryAuditAdmin)


class AuditItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'audit', 'product', 'system_count', 'physical_count', 'discrepancy', 'adjustment_reason', 'adjustment_status')
    list_filter = ('audit__audit_date', 'adjustment_status', 'adjustment_reason', 'audit')
    search_fields = ('product__name', 'product__barcode', 'audit__id')
    readonly_fields = ('discrepancy', 'created_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Audit & Product', {
            'fields': ('audit', 'product')
        }),
        ('Counts', {
            'fields': ('system_count', 'physical_count', 'discrepancy'),
            'description': 'Discrepancy is auto-calculated as physical - system'
        }),
        ('Adjustment', {
            'fields': ('adjustment_reason', 'adjustment_status', 'notes')
        }),
        ('Timeline', {
            'fields': ('created_at', 'verified_by', 'approved_by')
        }),
    )

admin.site.register(AuditItem, AuditItemAdmin)


class AdjustmentTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'adjustment_reason', 'quantity_adjusted', 'unit_cost', 'total_value', 'status', 'applied_at')
    list_filter = ('status', 'adjustment_reason', 'created_at')
    search_fields = ('product__name', 'product__barcode', 'id')
    readonly_fields = ('total_value', 'created_at', 'applied_at', 'audit_item')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Adjustment Details', {
            'fields': ('audit_item', 'product', 'adjustment_reason', 'quantity_adjusted')
        }),
        ('Costs', {
            'fields': ('unit_cost', 'total_value')
        }),
        ('Status', {
            'fields': ('status', 'recorded_by', 'applied_by', 'applied_at')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
    
    actions = ['mark_as_applied', 'mark_as_cancelled']
    
    def mark_as_applied(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='pending').update(status='applied', applied_at=timezone.now())
        self.message_user(request, f'{updated} adjustment(s) marked as applied.')
    mark_as_applied.short_description = 'Mark selected as Applied'
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} adjustment(s) marked as cancelled.')
    mark_as_cancelled.short_description = 'Mark selected as Cancelled'

admin.site.register(AdjustmentTransaction, AdjustmentTransactionAdmin)

