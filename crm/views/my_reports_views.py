from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, F, Q, Count
from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models.functions import Cast, TruncDate, Coalesce
from django.db.models import DecimalField, Value
from crm.models import Sale, saleItem
from scm.models import PurchaseOrder, PurchaseOrderItem
from im.models import Product, ProductABCMetrics, InventoryUnit
from crm.decorators import role_required


@login_required
@role_required('Admin', 'Manager', 'Auditor')
def my_reports(request):
    days = int(request.GET.get('days', 30))
    context = {
        'title': 'My Reports',
        'days': days,
    }
    return render(request, 'crm/reports/my_reports.html', context)


@login_required
@role_required('Admin', 'Manager', 'Auditor')
def my_reports_data(request):
    days = int(request.GET.get('days', 30))
    product_id = request.GET.get('product_id')

    end_date = timezone.localtime(timezone.now())
    start_date = end_date - timedelta(days=days)

    data = {}

    # --- 1. Trend data: daily sales, cost, profit ---
    daily_data = (
        saleItem.objects
        .filter(sale__date_created__gte=start_date, sale__date_created__lte=end_date)
        .annotate(date=TruncDate('sale__date_created'))
        .values('date')
        .annotate(
            sales_total=Sum(F('price') * Cast('quantity', output_field=DecimalField(max_digits=10, decimal_places=0))),
        )
        .order_by('date')
    )

    # Build date range series
    date_series = []
    sales_series = []
    cost_series = []
    profit_series = []

    date_map = {}
    for d in daily_data:
        date_map[d['date']] = {
            'sales': float(d['sales_total'] or 0),
        }

    current = start_date.date()
    total_sales = 0
    total_cost = 0
    while current <= end_date.date():
        entry = date_map.get(current, {'sales': 0})
        date_str = current.strftime('%Y-%m-%d')
        date_series.append(date_str)
        sales_series.append(entry['sales'])
        # Cost estimated from product.costo for the items sold that day
        cost_series.append(0)
        profit_series.append(0)
        current += timedelta(days=1)

    # Get costs per day for accuracy
    cost_data = (
        saleItem.objects
        .filter(sale__date_created__gte=start_date, sale__date_created__lte=end_date, cost__isnull=False)
        .exclude(cost='')
        .annotate(date=TruncDate('sale__date_created'))
        .values('date')
        .annotate(
            cost_total=Sum(
                Coalesce(Cast('cost', output_field=DecimalField(max_digits=10, decimal_places=2)), Value(Decimal('0')))
                * Cast('quantity', output_field=DecimalField(max_digits=10, decimal_places=0))
            ),
        )
        .order_by('date')
    )

    cost_map = {}
    for d in cost_data:
        if d['cost_total']:
            cost_map[d['date']] = float(d['cost_total'])

    for i, date_str in enumerate(date_series):
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        cost_val = cost_map.get(dt, 0)
        cost_series[i] = cost_val
        profit_series[i] = round(sales_series[i] - cost_val, 2)

    data['trend'] = {
        'labels': date_series,
        'sales': sales_series,
        'costs': cost_series,
        'profits': profit_series,
    }

    # --- 2. Inventory value ---
    total_inventory_value = Product.total_inventory_value()
    ready_count = InventoryUnit.objects.filter(status='ready_to_sale').count()

    data['inventory'] = {
        'total_value': float(total_inventory_value),
        'total_units': ready_count,
    }

    # --- 3. Product lookup ---
    if product_id:
        try:
            product = Product.objects.get(id=product_id)
        except (Product.DoesNotExist, ValueError):
            try:
                product = Product.objects.get(barcode=product_id)
            except Product.DoesNotExist:
                data['product'] = None
                return JsonResponse(data)

        # ABC classification
        abc = ProductABCMetrics.objects.filter(product=product).first()

        # Last purchase
        last_purchase = (
            PurchaseOrderItem.objects
            .filter(product=product, purchase_order__status='completed')
            .order_by('-purchase_order__completed_date')
            .first()
        )

        # Last sale
        last_sale = (
            saleItem.objects
            .filter(product=product)
            .order_by('-date_created')
            .first()
        )

        # Sale trend (last 30 days sales qty)
        sale_trend_data = (
            saleItem.objects
            .filter(product=product, sale__date_created__gte=timezone.now() - timedelta(days=30))
            .annotate(date=TruncDate('sale__date_created'))
            .values('date')
            .annotate(qty=Sum(Cast('quantity', output_field=DecimalField(max_digits=10, decimal_places=0))))
            .order_by('date')
        )

        trend_labels = []
        trend_qty = []
        trend_map = {}
        for d in sale_trend_data:
            trend_map[d['date']] = int(d['qty'] or 0)

        sd = (timezone.now() - timedelta(days=30)).date()
        ed = timezone.now().date()
        c = sd
        while c <= ed:
            trend_labels.append(c.strftime('%Y-%m-%d'))
            trend_qty.append(trend_map.get(c, 0))
            c += timedelta(days=1)

        data['product'] = {
            'id': product.id,
            'name': product.full_name,
            'barcode': product.barcode,
            'stock': product.stock_ready_to_sale,
            'abc': abc.abc_classification if abc else 'N/A',
            'abc_revenue': float(abc.last_30_days_revenue) if abc and abc.last_30_days_revenue else 0,
            'last_purchase_date': last_purchase.purchase_order.completed_date.strftime('%Y-%m-%d %H:%M') if last_purchase and last_purchase.purchase_order.completed_date else 'N/A',
            'last_purchase_qty': last_purchase.ordered_quantity if last_purchase else 0,
            'last_sale_date': last_sale.date_created.strftime('%Y-%m-%d %H:%M') if last_sale and last_sale.date_created else 'N/A',
            'last_sale_qty': int(last_sale.quantity) if last_sale else 0,
            'trend_labels': trend_labels,
            'trend_qty': trend_qty,
        }

    return JsonResponse(data)
