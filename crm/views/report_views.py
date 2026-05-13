from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, F, Q
from datetime import datetime, timedelta
from decimal import Decimal
from crm.models import Sale, saleItem, Devolution, devolutionItem
from im.models import InventoryUnit
from crm.decorators import role_required


@login_required
@role_required('Admin', 'Manager', 'Auditor')
def daily_report(request):
    """Generate daily sales report with FIFO costing"""
    
    # Get date filter
    today = timezone.localtime(timezone.now()).date()
    date_from = request.GET.get('date_from', today.strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))
    
    date_range_data = {}
    
    try:
        from_date = datetime.strptime(date_from, '%Y-%m-%d')
        to_date = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
        
        current_tz = timezone.get_current_timezone()
        from_datetime = timezone.make_aware(from_date, current_tz)
        to_datetime = timezone.make_aware(to_date, current_tz)
        
        # Get sales for the date range
        sales = Sale.objects.filter(
            date_created__gte=from_datetime,
            date_created__lt=to_datetime
        )
        
        # Get devolutions for the date range
        devolutions = Devolution.objects.filter(
            date_created__gte=from_datetime,
            date_created__lt=to_datetime
        )
        
        # Calculate totals by tipo
        date_range_data = {
            'date_from': from_datetime.date(),
            'date_to': to_datetime.date() - timedelta(days=1),
            'totals': calculate_report_totals(sales, devolutions),
        }
        
    except ValueError:
        pass
    
    context = {
        'title': 'Daily Report',
        'date_from': date_from,
        'date_to': date_to,
        'report_data': date_range_data,
    }
    
    return render(request, 'crm/reports/daily_report.html', context)


def calculate_report_totals(sales, devolutions):
    """Calculate sales, devolutions, and profit totals by tipo with retail KPIs"""
    
    totals = {
        'menudeo': {
            'sales_count': 0,
            'sales_total': Decimal('0'),
            'sales_cost': Decimal('0'),
            'sales_cost_fifo': Decimal('0'),
            'sales_cost_financial': Decimal('0'),
            'items_sold': 0,
            'devolutions_count': 0,
            'devolutions_total': Decimal('0'),
            'devolutions_cost': Decimal('0'),
            'devolution_cost_fifo': Decimal('0'),
            'devolution_cost_financial': Decimal('0'),
            'devolution_items': 0,
            'net_sales': Decimal('0'),
            'cost_of_goods': Decimal('0'),
            'cost_of_goods_fifo': Decimal('0'),
            'cost_of_goods_financial': Decimal('0'),
            'gross_profit': Decimal('0'),
            'gross_profit_margin': Decimal('0'),
            'fifo_gross_profit': Decimal('0'),
            'fifo_gross_profit_margin': Decimal('0'),
            'financial_gross_profit': Decimal('0'),
            'financial_gross_profit_margin': Decimal('0'),
            'avg_transaction_value': Decimal('0'),
            'return_rate': Decimal('0'),
        },
        'mayoreo': {
            'sales_count': 0,
            'sales_total': Decimal('0'),
            'sales_cost': Decimal('0'),
            'sales_cost_fifo': Decimal('0'),
            'sales_cost_financial': Decimal('0'),
            'items_sold': 0,
            'devolutions_count': 0,
            'devolutions_total': Decimal('0'),
            'devolutions_cost': Decimal('0'),
            'devolution_cost_fifo': Decimal('0'),
            'devolution_cost_financial': Decimal('0'),
            'devolution_items': 0,
            'net_sales': Decimal('0'),
            'cost_of_goods': Decimal('0'),
            'cost_of_goods_fifo': Decimal('0'),
            'cost_of_goods_financial': Decimal('0'),
            'gross_profit': Decimal('0'),
            'gross_profit_margin': Decimal('0'),
            'fifo_gross_profit': Decimal('0'),
            'fifo_gross_profit_margin': Decimal('0'),
            'financial_gross_profit': Decimal('0'),
            'financial_gross_profit_margin': Decimal('0'),
            'avg_transaction_value': Decimal('0'),
            'return_rate': Decimal('0'),
        },
        'combined': {
            'sales_count': 0,
            'sales_total': Decimal('0'),
            'sales_cost': Decimal('0'),
            'sales_cost_fifo': Decimal('0'),
            'sales_cost_financial': Decimal('0'),
            'items_sold': 0,
            'devolutions_count': 0,
            'devolutions_total': Decimal('0'),
            'devolutions_cost': Decimal('0'),
            'devolution_cost_fifo': Decimal('0'),
            'devolution_cost_financial': Decimal('0'),
            'devolution_items': 0,
            'net_sales': Decimal('0'),
            'cost_of_goods': Decimal('0'),
            'cost_of_goods_fifo': Decimal('0'),
            'cost_of_goods_financial': Decimal('0'),
            'gross_profit': Decimal('0'),
            'gross_profit_margin': Decimal('0'),
            'fifo_gross_profit': Decimal('0'),
            'fifo_gross_profit_margin': Decimal('0'),
            'financial_gross_profit': Decimal('0'),
            'financial_gross_profit_margin': Decimal('0'),
            'avg_transaction_value': Decimal('0'),
            'return_rate': Decimal('0'),
        }
    }
    
    # Process sales
    for sale in sales.prefetch_related('saleitem_set'):
        sale_tipo = sale.tipo
        items = sale.saleitem_set.all()
        
        # For POS sales: use total_amount which is the single source of truth
        # For manual sales: fall back to calculating from items (cost/margen)
        if sale.total_amount and sale.total_amount > 0:
            # POS or modern sales with backend-calculated total_amount
            sale_total = Decimal(str(sale.total_amount))
            
            # Estimate cost from items if available
            sale_cost = Decimal('0')
            sale_cost_fifo = Decimal('0')
            sale_cost_financial = Decimal('0')
            items_count = 0
            
            for item in items:
                try:
                    quantity = int(item.quantity)
                    items_count += quantity
                    
                    # If cost is available, use it; otherwise estimate from product cost
                    if item.cost:
                        cost = Decimal(str(item.cost))
                        sale_cost += cost * quantity
                    else:
                        # For POS items without cost field, estimate from product cost
                        product = item.product
                        if product and product.costo:
                            product_cost = Decimal(str(product.costo))
                            sale_cost += product_cost * quantity
                    
                    # FIFO cost from inventory units
                    if item.product:
                        fifo_cost = get_fifo_cost(item.product, quantity)
                        sale_cost_fifo += fifo_cost
                        # Financial cost using product.costo
                        if item.product.costo:
                            financial_cost = Decimal(str(item.product.costo)) * quantity
                            sale_cost_financial += financial_cost
                except (ValueError, TypeError):
                    pass
        else:
            # Legacy sales: calculate from cost and margin fields
            sale_total = Decimal('0')
            sale_cost = Decimal('0')
            sale_cost_fifo = Decimal('0')
            sale_cost_financial = Decimal('0')
            items_count = 0
            
            for item in items:
                try:
                    quantity = int(item.quantity)
                    
                    if item.cost:
                        cost = Decimal(str(item.cost))
                        margen = Decimal(str(item.margen)) if item.margen else Decimal('0')
                        price = cost * (1 + margen)
                        
                        sale_total += price * quantity
                        items_count += quantity
                        sale_cost += cost * quantity
                    else:
                        price = Decimal('0')
                    
                    # FIFO cost from inventory units
                    if item.product:
                        fifo_cost = get_fifo_cost(item.product, quantity)
                        sale_cost_fifo += fifo_cost
                        # Financial cost using product.costo
                        if item.product.costo:
                            financial_cost = Decimal(str(item.product.costo)) * quantity
                            sale_cost_financial += financial_cost
                    
                except (ValueError, TypeError):
                    pass
        
        totals[sale_tipo]['sales_count'] += 1
        totals[sale_tipo]['sales_total'] += sale_total
        totals[sale_tipo]['sales_cost'] += sale_cost
        totals[sale_tipo]['sales_cost_fifo'] += sale_cost_fifo
        totals[sale_tipo]['sales_cost_financial'] += sale_cost_financial
        totals[sale_tipo]['items_sold'] += items_count
    
    # Process devolutions
    for devolution in devolutions.prefetch_related('devolutionitem_set'):
        dev_tipo = devolution.tipo
        items = devolution.devolutionitem_set.all()
        
        dev_total = Decimal('0')
        dev_cost = Decimal('0')
        dev_cost_fifo = Decimal('0')
        dev_cost_financial = Decimal('0')
        items_count = 0
        
        for item in items:
            try:
                quantity = int(item.quantity)
                
                # Calculate price from cost and margin
                if item.cost:
                    cost = Decimal(str(item.cost))
                    margen = Decimal(str(item.margen)) if item.margen else Decimal('0')
                    price = cost * (1 + margen)
                    
                    # Use item.cost directly for profit (cost at time of devolution)
                    dev_total += price * quantity
                    items_count += quantity
                    dev_cost += cost * quantity
                else:
                    price = Decimal('0')
                
                # FIFO cost from inventory units
                if item.product:
                    fifo_cost = get_fifo_cost(item.product, quantity)
                    dev_cost_fifo += fifo_cost
                    # Financial cost using product.costo
                    if item.product.costo:
                        financial_cost = Decimal(str(item.product.costo)) * quantity
                        dev_cost_financial += financial_cost
                
            except (ValueError, TypeError):
                pass
        
        totals[dev_tipo]['devolutions_count'] += 1
        totals[dev_tipo]['devolutions_total'] += dev_total
        totals[dev_tipo]['devolutions_cost'] += dev_cost
        totals[dev_tipo]['devolution_cost_fifo'] += dev_cost_fifo
        totals[dev_tipo]['devolution_cost_financial'] += dev_cost_financial
        totals[dev_tipo]['devolution_items'] += items_count
    
    # Calculate KPIs for each tipo
    for tipo in ['menudeo', 'mayoreo']:
        net_sales = totals[tipo]['sales_total'] - totals[tipo]['devolutions_total']
        cost_of_goods = totals[tipo]['sales_cost'] - totals[tipo]['devolutions_cost']
        cost_of_goods_fifo = totals[tipo]['sales_cost_fifo'] - totals[tipo]['devolution_cost_fifo']
        cost_of_goods_financial = totals[tipo]['sales_cost_financial'] - totals[tipo]['devolution_cost_financial']
        gross_profit = net_sales - cost_of_goods
        fifo_gross_profit = net_sales - cost_of_goods_fifo
        financial_gross_profit = net_sales - cost_of_goods_financial
        
        totals[tipo]['net_sales'] = net_sales
        totals[tipo]['cost_of_goods'] = cost_of_goods
        totals[tipo]['cost_of_goods_fifo'] = cost_of_goods_fifo
        totals[tipo]['cost_of_goods_financial'] = cost_of_goods_financial
        totals[tipo]['gross_profit'] = gross_profit
        totals[tipo]['fifo_gross_profit'] = fifo_gross_profit
        totals[tipo]['financial_gross_profit'] = financial_gross_profit
        
        # Gross Profit Margin % = (Gross Profit / Sales) * 100
        if totals[tipo]['sales_total'] > 0:
            gross_profit_margin = (gross_profit / totals[tipo]['sales_total']) * 100
            totals[tipo]['gross_profit_margin'] = round(gross_profit_margin, 2)
            fifo_margin = (fifo_gross_profit / totals[tipo]['sales_total']) * 100
            totals[tipo]['fifo_gross_profit_margin'] = round(fifo_margin, 2)
            financial_margin = (financial_gross_profit / totals[tipo]['sales_total']) * 100
            totals[tipo]['financial_gross_profit_margin'] = round(financial_margin, 2)
        
        # Average Transaction Value = Sales / Number of Transactions
        if totals[tipo]['sales_count'] > 0:
            avg_transaction_value = totals[tipo]['sales_total'] / totals[tipo]['sales_count']
            totals[tipo]['avg_transaction_value'] = round(avg_transaction_value, 2)
        
        # Return Rate % = (Devolution Items / Sales Items) * 100
        if totals[tipo]['items_sold'] > 0:
            return_rate = (totals[tipo]['devolution_items'] / totals[tipo]['items_sold']) * 100
            totals[tipo]['return_rate'] = round(return_rate, 2)
    
    # Calculate combined totals and KPIs
    for field in ['sales_count', 'sales_total', 'sales_cost', 'sales_cost_fifo', 'sales_cost_financial',
                  'items_sold', 'devolutions_count', 'devolutions_total', 'devolutions_cost',
                  'devolution_cost_fifo', 'devolution_cost_financial', 'devolution_items']:
        totals['combined'][field] = totals['menudeo'][field] + totals['mayoreo'][field]
    
    net_sales = totals['combined']['sales_total'] - totals['combined']['devolutions_total']
    cost_of_goods = totals['combined']['sales_cost'] - totals['combined']['devolutions_cost']
    cost_of_goods_fifo = totals['combined']['sales_cost_fifo'] - totals['combined']['devolution_cost_fifo']
    cost_of_goods_financial = totals['combined']['sales_cost_financial'] - totals['combined']['devolution_cost_financial']
    gross_profit = net_sales - cost_of_goods
    fifo_gross_profit = net_sales - cost_of_goods_fifo
    financial_gross_profit = net_sales - cost_of_goods_financial
    
    totals['combined']['net_sales'] = net_sales
    totals['combined']['cost_of_goods'] = cost_of_goods
    totals['combined']['cost_of_goods_fifo'] = cost_of_goods_fifo
    totals['combined']['cost_of_goods_financial'] = cost_of_goods_financial
    totals['combined']['gross_profit'] = gross_profit
    totals['combined']['fifo_gross_profit'] = fifo_gross_profit
    totals['combined']['financial_gross_profit'] = financial_gross_profit
    
    if totals['combined']['sales_total'] > 0:
        gross_profit_margin = (gross_profit / totals['combined']['sales_total']) * 100
        totals['combined']['gross_profit_margin'] = round(gross_profit_margin, 2)
        fifo_margin = (fifo_gross_profit / totals['combined']['sales_total']) * 100
        totals['combined']['fifo_gross_profit_margin'] = round(fifo_margin, 2)
        financial_margin = (financial_gross_profit / totals['combined']['sales_total']) * 100
        totals['combined']['financial_gross_profit_margin'] = round(financial_margin, 2)
    
    if totals['combined']['sales_count'] > 0:
        avg_transaction_value = totals['combined']['sales_total'] / totals['combined']['sales_count']
        totals['combined']['avg_transaction_value'] = round(avg_transaction_value, 2)
    
    if totals['combined']['items_sold'] > 0:
        return_rate = (totals['combined']['devolution_items'] / totals['combined']['items_sold']) * 100
        totals['combined']['return_rate'] = round(return_rate, 2)
    
    return totals


def get_fifo_cost(product, quantity):
    """Calculate cost of goods using FIFO (First In First Out) method"""
    if not product or quantity <= 0:
        return Decimal('0')
    
    try:
        # Get inventory units ordered by received date (FIFO)
        inventory_units = InventoryUnit.objects.filter(
            product=product,
            status='ready_to_sale'
        ).order_by('received_date')
        
        total_cost = Decimal('0')
        units_needed = quantity
        
        for unit in inventory_units:
            if units_needed <= 0:
                break
            
            # Use the purchase cost from this inventory unit
            unit_cost = Decimal(str(unit.purchase_cost)) if unit.purchase_cost else Decimal('0')
            total_cost += unit_cost
            units_needed -= 1
        
        # If not enough inventory units, use product cost as fallback
        if units_needed > 0:
            fallback_cost = Decimal(str(product.costo)) if product.costo else Decimal('0')
            total_cost += fallback_cost * units_needed
        
        return total_cost
        
    except (AttributeError, ValueError):
        # Fallback to product cost if inventory tracking unavailable
        return Decimal(str(product.costo)) * quantity if product.costo else Decimal('0')
