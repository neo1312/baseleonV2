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
from im.models import Product, ProductABCMetrics
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

    # --- 1. Trend data: daily sales ---
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
    cost_fifo_series = []
    cost_accounting_series = []
    profit_fifo_series = []
    profit_accounting_series = []

    date_map = {}
    for d in daily_data:
        date_map[d['date']] = {
            'sales': float(d['sales_total'] or 0),
        }

    current = start_date.date()
    while current <= end_date.date():
        entry = date_map.get(current, {'sales': 0})
        date_series.append(current.strftime('%Y-%m-%d'))
        sales_series.append(entry['sales'])
        cost_fifo_series.append(0)
        cost_accounting_series.append(0)
        profit_fifo_series.append(0)
        profit_accounting_series.append(0)
        current += timedelta(days=1)

    # --- FIFO cost (financial): actual purchase_cost of InventoryUnits sold ---
    from im.models import InventoryUnit
    fifo_data = (
        InventoryUnit.objects
        .filter(
            sale_item__sale__date_created__gte=start_date,
            sale_item__sale__date_created__lte=end_date,
            status='sold',
            sale_item__isnull=False,
        )
        .annotate(date=TruncDate('sale_item__sale__date_created'))
        .values('date')
        .annotate(cost_total=Sum('purchase_cost'))
        .order_by('date')
    )
    fifo_map = {}
    for d in fifo_data:
        if d['cost_total']:
            fifo_map[d['date']] = float(d['cost_total'])

    # --- Accounting cost: saleItem.quantity * Product.costo (current product cost) ---
    accounting_data = (
        saleItem.objects
        .filter(sale__date_created__gte=start_date, sale__date_created__lte=end_date)
        .annotate(date=TruncDate('sale__date_created'))
        .values('date')
        .annotate(
            cost_total=Sum(
                Cast('quantity', output_field=DecimalField(max_digits=10, decimal_places=0))
                * Coalesce('product__costo', Value(Decimal('0')))
            ),
        )
        .order_by('date')
    )
    accounting_map = {}
    for d in accounting_data:
        if d['cost_total']:
            accounting_map[d['date']] = float(d['cost_total'])

    for i, date_str in enumerate(date_series):
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        fifo_val = fifo_map.get(dt, 0)
        accounting_val = accounting_map.get(dt, 0)
        cost_fifo_series[i] = fifo_val
        cost_accounting_series[i] = accounting_val
        profit_fifo_series[i] = round(sales_series[i] - fifo_val, 2)
        profit_accounting_series[i] = round(sales_series[i] - accounting_val, 2)

    data['trend'] = {
        'labels': date_series,
        'sales': sales_series,
        'cost_fifo': cost_fifo_series,
        'cost_accounting': cost_accounting_series,
        'profit_fifo': profit_fifo_series,
        'profit_accounting': profit_accounting_series,
    }

    # --- 2. Product lookup ---
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


@login_required
@role_required('Admin', 'Manager', 'Auditor')
def inventory_value(request):
    from im.models import InventoryUnit
    from django.db.models import Sum

    # Financial (FIFO): sum of actual purchase_cost of ready_to_sale units
    fifo_value = InventoryUnit.objects.filter(
        status='ready_to_sale',
        purchase_cost__gt=0,
    ).aggregate(total=Sum('purchase_cost'))['total'] or 0

    # Accounting: ready_count * product.costo (current cost)
    accounting_value = Product.total_inventory_value()
    ready_count = InventoryUnit.objects.filter(status='ready_to_sale').count()

    return JsonResponse({
        'fifo_value': float(fifo_value),
        'accounting_value': float(accounting_value),
        'total_units': ready_count,
    })
