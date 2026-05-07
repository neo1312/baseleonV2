#inventory/models.py
from django.db.models import Sum
from django.db import models
from datetime import  timedelta, date
from django.utils import timezone
from decimal import Decimal
import math
from django.db.models.functions import Lower

class Brand(models.Model):
    id=models.AutoField(primary_key=True)
    name=models.CharField(max_length=100000,verbose_name='brand',unique=True)

#utility fields
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return '{}'.format(self.name,)

    def save(self, *args, **kwargs):
            if self.date_created is None:
                self.date_created = timezone.localtime(timezone.now())
            self.last_updated = timezone.localtime(timezone.now())
            super (Brand, self).save(*args,**kwargs)

    class Meta:
        verbose_name = 'brand'
        verbose_name_plural = 'brands'
        ordering = [Lower('name')]

class Category(models.Model):
    #Basic Fields
    id=models.CharField(primary_key=True,max_length=100)
    name = models.CharField(max_length=150, verbose_name='name', unique=True)

    #utility fields
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return '{}'.format(self.name)

    def save(self, *args, **kwargs):
            if self.date_created is None:
                self.date_created = timezone.localtime(timezone.now())
            self.last_updated = timezone.localtime(timezone.now())
            super (Category, self).save(*args,**kwargs)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

class Product(models.Model):

    Pieza=1
    Gramos=2
    Metro=3

    unidad_choices=(
            ("Pieza","pieza"),
            ("Gramos","gramos"),
            ("Metro","metro"),
            )

    id=models.AutoField(primary_key=True,verbose_name='id')
    active=models.BooleanField(default=True)
    sat=models.BooleanField(default=False)
    name=models.CharField(max_length=500,verbose_name='name')
    barcode=models.CharField(max_length=500,verbose_name='barcode',unique=True)
    stock=models.PositiveIntegerField(default=0,verbose_name='existencia')
    stockMax=models.PositiveIntegerField(default=0,verbose_name='stockMaximo')
    stockMin=models.PositiveIntegerField(default=0,verbose_name='stockMinimo')
    #image = models.ImageField(upload_to='product/%Y/%m/%d', null=True, blank=True)
    margen= models.CharField(max_length=100, verbose_name='margen',default=0)
    margenMayoreo= models.CharField(max_length=100, verbose_name='margenMayoreo',default=0.05)
    costo= models.DecimalField(max_digits=14,default=0.000000,decimal_places=6)
    granel= models.BooleanField(verbose_name='granel',default=False)
    minimo= models.PositiveIntegerField(verbose_name='minimo',default=0)
    margenGranel= models.CharField(max_length=100, verbose_name='margenGranel',default=0)
    unidad= models.CharField(max_length=100, verbose_name='unidad',default="Pieza",choices=unidad_choices)
    unidadEmpaque= models.CharField(max_length=100, verbose_name='unidadEmpaque',default="1")
    monedero_percentaje= models.CharField(max_length=100, verbose_name='monedero%',default=0.00)
    
    # Manual pricing fields (nullable - None means use calculated price)
    precio_manual = models.DecimalField(max_digits=14, default=None, decimal_places=2, null=True, blank=True, verbose_name='Precio Manual')
    precio_mayoreo_manual = models.DecimalField(max_digits=14, default=None, decimal_places=2, null=True, blank=True, verbose_name='Precio Mayoreo Manual')
    precio_granel_manual = models.DecimalField(max_digits=14, default=None, decimal_places=2, null=True, blank=True, verbose_name='Precio Granel Manual')
    
    # Pricing mode selectors (margin vs manual price)
    pricing_mode = models.CharField(max_length=10, verbose_name='Modo Precio Regular', default='margin', choices=[('margin', 'Usar Margen'), ('price', 'Usar Precio Manual')])
    mayoreo_pricing_mode = models.CharField(max_length=10, verbose_name='Modo Precio Mayoreo', default='margin', choices=[('margin', 'Usar Margen'), ('price', 'Usar Precio Manual')])
    granel_pricing_mode = models.CharField(max_length=10, verbose_name='Modo Precio Granel', default='margin', choices=[('margin', 'Usar Margen'), ('price', 'Usar Precio Manual')])
    
    #foreing Fields
    category = models.ForeignKey(Category, on_delete=models.SET_NULL,null=True)
    provedor =models.ForeignKey('scm.Provider', on_delete=models.CASCADE,null=True)
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL,null=True)
    inventory_no = models.IntegerField(default=1)

  #utility fields
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    
    def unidad_verbose(self):
        return self.get_unidad_display()

    def __str__(self):
        return '{}'.format(self.name)



    def save(self, *args, **kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        
        # Handle pricing logic based on mode selection
        try:
            costo = float(self.costo) if self.costo else 0
            
            # === REGULAR PRICING ===
            if self.pricing_mode == 'price':
                # User wants to set manual price - calculate margin from it
                if self.precio_manual is not None and self.precio_manual > 0:
                    calculated_margin = (float(self.precio_manual) / costo - 1) if costo > 0 else 0
                    self.margen = str(calculated_margin)
            else:  # pricing_mode == 'margin'
                # User wants to use margin - clear manual price
                self.precio_manual = None
            
            # === MAYOREO PRICING ===
            if self.mayoreo_pricing_mode == 'price':
                # User wants to set manual mayoreo price - calculate margin from it
                if self.precio_mayoreo_manual is not None and self.precio_mayoreo_manual > 0:
                    calculated_margin_mayoreo = (float(self.precio_mayoreo_manual) / costo - 1) if costo > 0 else 0
                    self.margenMayoreo = str(calculated_margin_mayoreo)
            else:  # mayoreo_pricing_mode == 'margin'
                # User wants to use margin - clear manual price
                self.precio_mayoreo_manual = None
            
            # === GRANEL PRICING ===
            if self.granel:
                if self.granel_pricing_mode == 'price':
                    # User wants to set manual granel price - calculate margin from it
                    if self.precio_granel_manual is not None and self.precio_granel_manual > 0:
                        calculated_margin_granel = (float(self.precio_granel_manual) / costo - 1) if costo > 0 else 0
                        self.margenGranel = str(calculated_margin_granel)
                else:  # granel_pricing_mode == 'margin'
                    # User wants to use margin - clear manual price
                    self.precio_granel_manual = None
            else:
                # If granel is disabled, clear manual granel price and reset mode to default
                self.precio_granel_manual = None
                self.granel_pricing_mode = 'margin'
                
        except (ValueError, TypeError):
            pass
        
        super(Product, self).save(*args, **kwargs)

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['brand']
        constraints = [
            models.UniqueConstraint(fields=['category', 'brand', 'name'], name='unique_product_full_name')
        ]

    @property
    def full_name(self):
        category_name = self.category.name if self.category else ''
        brand_name = self.brand.name if self.brand else ''
        return f"{category_name} {self.name} {brand_name}"
    
    @property
    def semi_full_name(self):
        category_name = self.category.name if self.category else ''
        brand_name = self.brand.name if self.brand else ''
        return f"{category_name} {self.name} "
    
    @property
    def stock_ready_to_sale(self):
        """Calculate available inventory units in ready_to_sale status"""
        from im.models import InventoryUnit
        return InventoryUnit.objects.filter(
            product=self,
            status='ready_to_sale'
        ).count()

    @classmethod
    def total_inventory_value(cls):
        from django.db.models import Sum, F
        return cls.objects.aggregate(total_value=Sum(F('stock') * F('costo')))['total_value'] or 0
    
    def update_average_cost(self):
        """Calculate and update product cost based on average of all provider costs"""
        provider_costs = self.provider_pairs.all().values_list('provider_cost', flat=True)
        
        if provider_costs:
            average_cost = sum(Decimal(str(cost)) for cost in provider_costs) / len(provider_costs)
            self.costo = average_cost
            # Save without triggering recursive update
            Product.objects.filter(pk=self.pk).update(costo=average_cost)
        
        return self.costo
    
    def get_pv1(self, provider=None):
        """Get PV1 for a specific provider or the first provider if none specified"""
        if provider:
            pp = self.provider_pairs.filter(provider=provider).first()
            return pp.pv1 if pp else None
        
        pp = self.provider_pairs.first()
        return pp.pv1 if pp else None
    
    def get_provider_cost(self, provider=None):
        """Get provider-specific cost or fall back to product cost"""
        if provider:
            pp = self.provider_pairs.filter(provider=provider).first()
            return Decimal(str(pp.provider_cost)) if pp else Decimal(str(self.costo or 0))
        
        pp = self.provider_pairs.first()
        return Decimal(str(pp.provider_cost)) if pp else Decimal(str(self.costo or 0))

    @property
    def priceLista(self):
        # Use manual price if set
        if self.precio_manual is not None and self.precio_manual > 0:
            return float(self.precio_manual)
        
        if self.costo is None or self.margen is None:
            return 0

        costo=float(self.costo)
        margen=float(self.margen)
        margeng=float(self.margenGranel)
        minimo=self.minimo
        if self.granel != True:
            precio=math.ceil(costo*(1+margen))
        else:
            if self.unidad=='Gramos':
                precio=math.ceil((costo*(1+margen))*1000)
            else:
                precio=math.ceil((costo*(1+margen))*float(minimo))
        return precio
    
    @property
    def priceMayoreo(self):
        # Use manual mayoreo price if set
        if self.precio_mayoreo_manual is not None and self.precio_mayoreo_manual > 0:
            return float(self.precio_mayoreo_manual)
        
        costo=float(self.costo)
        margen=float(self.margenMayoreo)
        precio=math.ceil((costo*(1+margen)))
        return precio

    @property
    def priceListaGranel(self):
        # Use manual granel price if set and granel is enabled
        if self.granel and self.precio_granel_manual is not None and self.precio_granel_manual > 0:
            return float(self.precio_granel_manual)
        
        costo=float(self.costo)
        margen=float(self.margenGranel)
        if self.granel==False:
            precio= 'N/A'
        elif self.unidad=='Gramos':
            precio=math.ceil((costo*(1+margen))*1000)
        elif self.unidad == 'Metro':
            precio=math.ceil(costo*(1.0+margen))
        else:
            precio1=costo*(1+margen)
            precio=round(precio1*2.0)/2.0
        return precio


    @property
    def faltante(self):
        if self.stock_ready_to_sale <= self.stockMin:
            a1= float(self.stockMax-self.stock_ready_to_sale)/float(self.unidadEmpaque)
            a=math.ceil(a1)
        else:
            a='no'
        return a
    @property
    def faltante1(self):
        from im.models import InventoryUnit
        
        # Get total stock_ready_to_sale for all products with same barcode
        products = Product.objects.filter(barcode=self.barcode)
        total_stock = 0
        for product in products:
            total_stock += product.stock_ready_to_sale
        
        # Get totals for min/max
        totals = products.aggregate(
                total_stock_min=Sum('stockMin'),
                total_stock_max=Sum('stockMax')
                )
        total_stock_min = totals['total_stock_min'] or 0
        total_stock_max = totals['total_stock_max'] or 0

        if total_stock <= total_stock_min:
            a1=float(total_stock_max-total_stock)/float(self.unidadEmpaque)
            a=math.ceil(a1)
        else:
            a='no'
        return a
    
    @property
    def monedero(self):
        return round((float(self.margen) * float(0.076)),4)





class Cost(models.Model):
    id=models.AutoField(primary_key=True)
    values=models.CharField(max_length=100000)
    product=models.ForeignKey(Product, on_delete=models.CASCADE)

#utility fields
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return '{}'.format(self.id,)

    def save(self, *args, **kwargs):
            if self.date_created is None:
                self.date_created = timezone.localtime(timezone.now())
            self.last_updated = timezone.localtime(timezone.now())
            super (Cost, self).save(*args,**kwargs)

    class Meta:
        verbose_name = 'Cost'
        verbose_name_plural = 'Costs'
        ordering = ['id']


class Margin(models.Model):
    id=models.AutoField(primary_key=True)
    values=models.CharField(max_length=100000,verbose_name='margin')
    product=models.ForeignKey(Product, on_delete=models.CASCADE)

#utility fields
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return '{}'.format(self.id,)

    def save(self, *args, **kwargs):
            if self.date_created is None:
                self.date_created = timezone.localtime(timezone.now())
            self.last_updated = timezone.localtime(timezone.now())
            super (Margin, self).save(*args,**kwargs)

    class Meta:
        verbose_name = 'Margin'
        verbose_name_plural = 'Margins'
        ordering = ['id']


class InventoryUnit(models.Model):
    STATUS_CHOICES = [
        ('ordered', 'Ordered'),
        ('send', 'Send'),
        ('received', 'Received'),
        ('ready_to_sale', 'Ready to Sale'),
        ('sold', 'Sold'),
        ('retired_stolen', 'Retired - Stolen'),
        ('retired_damaged', 'Retired - Damaged'),
        ('retired_warranty', 'Retired - Warranty Return'),
        ('retired_miscounted', 'Retired - System Miscounted'),
        ('retired_expired', 'Retired - Expired/Obsolete'),
        ('retired_shrinkage', 'Retired - Unknown Shrinkage'),
        ('retired_correction', 'Retired - Manual Correction'),
        ('retired_other', 'Retired - Other'),
    ]
    
    ABC_CHOICES = [
        ('A', 'A - High Value'),
        ('B', 'B - Medium Value'),
        ('C', 'C - Low Value'),
        ('unclassified', 'Unclassified'),
    ]
    
    tracking_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Tracking ID',
        db_index=True
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='inventory_units'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ordered',
        db_index=True
    )
    abc_classification = models.CharField(
        max_length=20,
        choices=ABC_CHOICES,
        default='unclassified',
        db_index=True
    )
    
    ordered_date = models.DateTimeField(blank=True, null=True)
    received_date = models.DateTimeField(blank=True, null=True)
    ready_date = models.DateTimeField(blank=True, null=True)
    sold_date = models.DateTimeField(blank=True, null=True)
    retired_date = models.DateTimeField(blank=True, null=True)
    
    purchase_cost = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal('0.00'),
        verbose_name='Purchase Cost',
        help_text='Cost per unit at time of purchase'
    )
    
    received_cost = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal('0.00'),
        null=True,
        blank=True,
        verbose_name='Received Cost',
        help_text='Actual cost per unit when received (may differ from purchase cost)'
    )
    
    purchase_order = models.ForeignKey(
        'scm.PurchaseOrder',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='inventory_units'
    )
    purchase_item = models.ForeignKey(
        'scm.purchaseItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_units'
    )
    sale_item = models.ForeignKey(
        'crm.saleItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_units'
    )
    
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f'{self.tracking_id} - {self.product.name} ({self.status})'
    
    def save(self, *args, **kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        super(InventoryUnit, self).save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Inventory Unit'
        verbose_name_plural = 'Inventory Units'
        ordering = ['-tracking_id']
        indexes = [
            models.Index(fields=['tracking_id']),
            models.Index(fields=['status']),
            models.Index(fields=['abc_classification']),
            models.Index(fields=['product', 'status']),
            models.Index(fields=['-date_created']),
        ]


class ABCConfiguration(models.Model):
    TIME_PERIOD_CHOICES = [
        (30, 'Last 30 days'),
        (90, 'Last 90 days'),
        (180, 'Last 6 months'),
        (365, 'Last 12 months'),
    ]
    
    id = models.AutoField(primary_key=True)
    time_period_days = models.IntegerField(
        choices=TIME_PERIOD_CHOICES,
        default=30,
        verbose_name='Time Period for ABC Calculation (days)'
    )
    pareto_a_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=80.00,
        verbose_name='A Class Revenue Threshold (%)',
        help_text='Percentage of revenue threshold for A classification (e.g., 80 for 80%)'
    )
    pareto_b_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=95.00,
        verbose_name='B Class Revenue Threshold (%)',
        help_text='Cumulative percentage threshold for B classification (e.g., 95 for 80-95%)'
    )
    auto_recalculate = models.BooleanField(
        default=True,
        verbose_name='Auto-recalculate after sales/devolutions',
        help_text='If enabled, ABC classification recalculates automatically after each transaction'
    )
    last_recalculation = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Last Recalculation Timestamp'
    )
    
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f'ABC Configuration (Period: {self.time_period_days}d)'
    
    def save(self, *args, **kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        super(ABCConfiguration, self).save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'ABC Configuration'
        verbose_name_plural = 'ABC Configuration'


class ProductABCMetrics(models.Model):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='abc_metrics',
        primary_key=True
    )
    abc_classification = models.CharField(
        max_length=20,
        choices=InventoryUnit.ABC_CHOICES,
        default='unclassified',
        db_index=True
    )
    last_30_days_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.00,
        verbose_name='Revenue (Last 30 days)'
    )
    last_30_days_units_sold = models.IntegerField(
        default=0,
        verbose_name='Units Sold (Last 30 days)'
    )
    cumulative_revenue_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name='Cumulative Revenue %'
    )
    
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f'{self.product.name} - {self.abc_classification}'
    
    def save(self, *args, **kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        super(ProductABCMetrics, self).save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Product ABC Metrics'
        verbose_name_plural = 'Product ABC Metrics'
        ordering = ['-abc_classification']


class ForecastConfiguration(models.Model):
    """Configuration for demand forecasting system"""
    
    id = models.AutoField(primary_key=True)
    
    # Exponential smoothing parameters
    alpha = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal('0.30'),
        verbose_name='Alpha (Smoothing Coefficient)',
        help_text='0.1-0.5: Higher = more responsive to recent changes'
    )
    beta = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal('0.10'),
        verbose_name='Beta (Trend Coefficient)',
        help_text='0.01-0.2: Higher = stronger trend influence'
    )
    
    # Forecast parameters
    lookback_period_days = models.IntegerField(
        default=90,
        verbose_name='Lookback Period (days)',
        help_text='Number of historical days to use for forecasting'
    )
    forecast_horizon_days = models.IntegerField(
        default=30,
        verbose_name='Forecast Horizon (days)',
        help_text='Number of days ahead to forecast'
    )
    
    # Seasonality
    include_seasonality = models.BooleanField(
        default=True,
        verbose_name='Include Seasonality Adjustment'
    )
    
    # Safety stock
    safety_stock_multiplier = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal('1.50'),
        verbose_name='Safety Stock Multiplier',
        help_text='1.5 = 50% safety buffer'
    )
    
    # Lead time
    supplier_lead_time_days = models.IntegerField(
        default=7,
        verbose_name='Supplier Lead Time (days)'
    )
    
    # Auto recalculation
    auto_recalculate = models.BooleanField(
        default=True,
        verbose_name='Auto-recalculate forecasts',
        help_text='Recalculate when new sales are recorded'
    )
    
    last_recalculation = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Last Recalculation'
    )
    
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f'Forecast Configuration (α={self.alpha}, β={self.beta})'
    
    def save(self, *args, **kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        super(ForecastConfiguration, self).save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Forecast Configuration'
        verbose_name_plural = 'Forecast Configuration'


class DemandForecast(models.Model):
    """Demand forecast for products"""
    
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='demand_forecast',
        primary_key=True
    )
    
    # Forecast values
    forecast_daily = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Daily Forecast'
    )
    forecast_30days = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='30-Day Forecast'
    )
    
    # Confidence and bounds
    confidence_level = models.IntegerField(
        default=0,
        verbose_name='Confidence Level (%)'
    )
    lower_bound = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Lower Bound (95% CI)'
    )
    upper_bound = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Upper Bound (95% CI)'
    )
    
    # Trend and error
    trend = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Trend Component'
    )
    mape = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0.00'),
        verbose_name='Mean Absolute % Error'
    )
    
    # Recommendations
    reorder_point = models.IntegerField(
        default=0,
        verbose_name='Recommended Reorder Point'
    )
    eoq = models.IntegerField(
        default=0,
        verbose_name='Economic Order Quantity'
    )
    
    # Metadata
    last_sales_data_count = models.IntegerField(
        default=0,
        verbose_name='Data Points Used'
    )
    
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f'{self.product.name} - Daily: {self.forecast_daily}, Confidence: {self.confidence_level}%'
    
    def save(self, *args, **kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        super(DemandForecast, self).save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Demand Forecast'
        verbose_name_plural = 'Demand Forecasts'
        ordering = ['-forecast_daily']


class ProductProvider(models.Model):
    """Provider-PV1 pairs for products with provider-specific costs. Each product can have multiple providers with their own PV1 codes and costs."""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='provider_pairs',
        verbose_name='Product'
    )
    provider = models.ForeignKey(
        'scm.Provider',
        on_delete=models.CASCADE,
        related_name='product_pairs',
        verbose_name='Provider'
    )
    pv1 = models.CharField(
        max_length=100,
        verbose_name='Provider PV1',
        help_text='This provider\'s internal SKU/code for this product'
    )
    provider_cost = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal('0.00'),
        verbose_name='Provider Cost',
        help_text='Cost per unit from this specific provider'
    )
    
    # Utility fields
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f'{self.product.name} - {self.provider.name}: {self.pv1}'
    
    def save(self, *args, **kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        
        is_new = self.pk is None
        old_cost = None
        
        if not is_new:
            old_pp = ProductProvider.objects.get(pk=self.pk)
            old_cost = old_pp.provider_cost
        
        super(ProductProvider, self).save(*args, **kwargs)
        
        # Recalculate product average cost
        if is_new or (old_cost and old_cost != self.provider_cost):
            self.product.update_average_cost()
    
    class Meta:
        verbose_name = 'Product Provider'
        verbose_name_plural = 'Product Providers'
        unique_together = ('product', 'provider')
        ordering = ['product', 'provider']


# Signal handlers for safe product deletion
from django.db.models.signals import post_delete
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)

@receiver(post_delete, sender=Product)
def product_post_delete(sender, instance, **kwargs):
    """Log product deletion for audit trail"""
    logger.info(f"Product deleted: ID={instance.id}, Name={instance.name}, Barcode={instance.barcode}")
    # ABC metrics and DemandForecast are auto-deleted via CASCADE
    # Sale/Devolution/PO items remain with null product reference

@receiver(post_delete, sender=ProductProvider)
def product_provider_post_delete(sender, instance, **kwargs):
    """Recalculate product average cost when a provider is removed"""
    try:
        instance.product.update_average_cost()
    except Exception as e:
        logger.error(f"Error updating product cost after provider deletion: {e}")


# ============================================================================
# INVENTORY AUDIT MODELS
# ============================================================================

class InventoryAudit(models.Model):
    """Represents an inventory audit cycle"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('under_review', 'Under Review'),
        ('completed', 'Completed'),
    ]
    
    AUDIT_TYPE_CHOICES = [
        ('random', 'Random Sample (20 items)'),
        ('random_custom', 'Random Sample (Custom Count)'),
        ('full', 'Full Inventory'),
        ('category', 'By Category'),
        ('manual', 'Manual Selection'),
    ]
    
    id = models.AutoField(primary_key=True)
    audit_date = models.DateField(auto_now_add=True, verbose_name='Audit Date')
    audit_type = models.CharField(max_length=20, choices=AUDIT_TYPE_CHOICES, verbose_name='Audit Type')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='Status')
    
    # Auditor info
    auditor = models.CharField(max_length=150, verbose_name='Auditor')
    reviewed_by = models.CharField(max_length=150, null=True, blank=True, verbose_name='Reviewed By')
    
    # Stats
    total_items_audited = models.IntegerField(default=0, verbose_name='Total Items Audited')
    total_discrepancies = models.IntegerField(default=0, verbose_name='Total Discrepancies')
    total_adjustment_value = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Total Adjustment Value')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Started At')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Completed At')
    
    # Notes
    notes = models.TextField(null=True, blank=True, verbose_name='Notes')
    
    class Meta:
        verbose_name = 'Inventory Audit'
        verbose_name_plural = 'Inventory Audits'
        ordering = ['-audit_date']
    
    def __str__(self):
        return f"Audit {self.id} ({self.get_audit_type_display()}) - {self.audit_date} - {self.get_status_display()}"
    
    def update_stats(self):
        """Recalculate audit statistics"""
        items = self.items.all()
        self.total_items_audited = items.count()
        # Count all non-zero discrepancies (both positive and negative)
        self.total_discrepancies = items.exclude(discrepancy=0).count()
        
        # Calculate total value of adjustments (at current cost)
        # Preserve sign: positive discrepancy (gain) = positive value, negative (loss) = negative value
        total_value = Decimal('0')
        for item in items.exclude(discrepancy=0):
            if item.product:
                qty = item.discrepancy  # Keep the sign!
                cost = item.product.costo or Decimal('0')
                total_value += Decimal(str(qty)) * Decimal(str(cost))
        
        self.total_adjustment_value = total_value
        self.save()



class AuditItem(models.Model):
    """Represents a product audited in an audit"""
    ADJUSTMENT_REASON_CHOICES = [
        ('stolen', 'Stolen'),
        ('damaged', 'Damaged/Unusable'),
        ('warranty', 'Warranty Return'),
        ('miscounted', 'System Miscounted'),
        ('expired', 'Expired/Obsolete'),
        ('shrinkage', 'Unknown Shrinkage'),
        ('correction', 'Manual Correction'),
        ('other', 'Other'),
    ]
    
    ADJUSTMENT_STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('applied', 'Applied'),
        ('rejected', 'Rejected'),
    ]
    
    id = models.AutoField(primary_key=True)
    audit = models.ForeignKey(InventoryAudit, on_delete=models.CASCADE, related_name='items', verbose_name='Audit')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Product')
    
    # Counts
    system_count = models.IntegerField(verbose_name='System Count')
    physical_count = models.IntegerField(verbose_name='Physical Count')
    discrepancy = models.IntegerField(verbose_name='Discrepancy')  # physical - system
    
    # Adjustment info
    adjustment_reason = models.CharField(
        max_length=20, 
        choices=ADJUSTMENT_REASON_CHOICES, 
        null=True, 
        blank=True,
        verbose_name='Adjustment Reason'
    )
    adjustment_status = models.CharField(
        max_length=20, 
        choices=ADJUSTMENT_STATUS_CHOICES, 
        default='pending',
        verbose_name='Adjustment Status'
    )
    
    # Notes
    notes = models.TextField(null=True, blank=True, verbose_name='Notes')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    verified_by = models.CharField(max_length=150, null=True, blank=True, verbose_name='Verified By')
    approved_by = models.CharField(max_length=150, null=True, blank=True, verbose_name='Approved By')
    
    class Meta:
        verbose_name = 'Audit Item'
        verbose_name_plural = 'Audit Items'
        unique_together = ('audit', 'product')
        ordering = ['product__name']
    
    def __str__(self):
        return f"{self.product.name if self.product else 'Unknown'} - Discrepancy: {self.discrepancy}"
    
    def save(self, *args, **kwargs):
        # Auto-calculate discrepancy
        self.discrepancy = self.physical_count - self.system_count
        super(AuditItem, self).save(*args, **kwargs)


class AdjustmentTransaction(models.Model):
    """Records the result of an approved audit adjustment"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('applied', 'Applied'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.AutoField(primary_key=True)
    audit_item = models.OneToOneField(AuditItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='adjustment', verbose_name='Audit Item')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Product')
    
    # Adjustment details
    adjustment_reason = models.CharField(max_length=20, verbose_name='Reason')
    quantity_adjusted = models.IntegerField(verbose_name='Quantity Adjusted')  # Can be negative
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Status')
    
    # Cost info
    unit_cost = models.DecimalField(max_digits=12, decimal_places=6, default=0, verbose_name='Unit Cost')
    total_value = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Total Adjustment Value')
    
    # Tracking
    recorded_by = models.CharField(max_length=150, verbose_name='Recorded By')
    applied_by = models.CharField(max_length=150, null=True, blank=True, verbose_name='Applied By')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    applied_at = models.DateTimeField(null=True, blank=True, verbose_name='Applied At')
    
    class Meta:
        verbose_name = 'Adjustment Transaction'
        verbose_name_plural = 'Adjustment Transactions'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Adjustment: {self.product.name if self.product else 'Unknown'} ({self.quantity_adjusted:+d} units)"
    
    def save(self, *args, **kwargs):
        # Calculate total value
        self.total_value = Decimal(str(self.quantity_adjusted)) * Decimal(str(self.unit_cost or 0))
        super(AdjustmentTransaction, self).save(*args, **kwargs)

