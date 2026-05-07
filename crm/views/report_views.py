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
        from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
        to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
        to_date = to_date + timedelta(days=1)  # Include entire end date
        
        # Get sales for the date range
        sales = Sale.objects.filter(
            date_created__date__gte=from_date,
            date_created__date__lt=to_date
        )
        
        # Get devolutions for the date range
        devolutions = Devolution.objects.filter(
            date_created__date__gte=from_date,
            date_created__date__lt=to_date
        )
        
        # Calculate totals by tipo
        date_range_data = {
            'date_from': from_date,
            'date_to': to_date - timedelta(days=1),
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
            'items_sold': 0,
            'devolutions_count': 0,
            'devolutions_total': Decimal('0'),
            'devolutions_cost': Decimal('0'),
            'devolution_items': 0,
            'net_sales': Decimal('0'),
            'cost_of_goods': Decimal('0'),
            'gross_profit': Decimal('0'),
            'gross_profit_margin': Decimal('0'),
            'avg_transaction_value': Decimal('0'),
            'return_rate': Decimal('0'),
        },
        'mayoreo': {
            'sales_count': 0,
            'sales_total': Decimal('0'),
            'sales_cost': Decimal('0'),
            'items_sold': 0,
            'devolutions_count': 0,
            'devolutions_total': Decimal('0'),
            'devolutions_cost': Decimal('0'),
            'devolution_items': 0,
            'net_sales': Decimal('0'),
            'cost_of_goods': Decimal('0'),
            'gross_profit': Decimal('0'),
            'gross_profit_margin': Decimal('0'),
            'avg_transaction_value': Decimal('0'),
            'return_rate': Decimal('0'),
        },
        'combined': {
            'sales_count': 0,
            'sales_total': Decimal('0'),
            'sales_cost': Decimal('0'),
            'items_sold': 0,
            'devolutions_count': 0,
            'devolutions_total': Decimal('0'),
            'devolutions_cost': Decimal('0'),
            'devolution_items': 0,
            'net_sales': Decimal('0'),
            'cost_of_goods': Decimal('0'),
            'gross_profit': Decimal('0'),
            'gross_profit_margin': Decimal('0'),
            'avg_transaction_value': Decimal('0'),
            'return_rate': Decimal('0'),
        }
    }
    
    # Process sales
    for sale in sales.prefetch_related('saleitem_set'):
        sale_tipo = sale.tipo
        items = sale.saleitem_set.all()
        
        sale_total = Decimal('0')
        sale_cost = Decimal('0')
        items_count = 0
        
        for item in items:
            try:
                quantity = int(item.quantity)
                
                # Calculate price from cost and margin (same logic as devolutions)
                if item.cost:
                    cost = Decimal(str(item.cost))
                    margen = Decimal(str(item.margen)) if item.margen else Decimal('0')
                    price = cost * (1 + margen)
                    
                    # Use item.cost directly for profit (cost at time of sale)
                    sale_total += price * quantity
                    items_count += quantity
                    sale_cost += cost * quantity
                else:
                    price = Decimal('0')
                
            except (ValueError, TypeError):
                pass
        
        totals[sale_tipo]['sales_count'] += 1
        totals[sale_tipo]['sales_total'] += sale_total
        totals[sale_tipo]['sales_cost'] += sale_cost
        totals[sale_tipo]['items_sold'] += items_count
    
    # Process devolutions
    for devolution in devolutions.prefetch_related('devolutionitem_set'):
        dev_tipo = devolution.tipo
        items = devolution.devolutionitem_set.all()
        
        dev_total = Decimal('0')
        dev_cost = Decimal('0')
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
                
            except (ValueError, TypeError):
                pass
        
        totals[dev_tipo]['devolutions_count'] += 1
        totals[dev_tipo]['devolutions_total'] += dev_total
        totals[dev_tipo]['devolutions_cost'] += dev_cost
        totals[dev_tipo]['devolution_items'] += items_count
    
    # Calculate KPIs for each tipo
    for tipo in ['menudeo', 'mayoreo']:
        net_sales = totals[tipo]['sales_total'] - totals[tipo]['devolutions_total']
        cost_of_goods = totals[tipo]['sales_cost'] - totals[tipo]['devolutions_cost']
        gross_profit = net_sales - cost_of_goods
        
        totals[tipo]['net_sales'] = net_sales
        totals[tipo]['cost_of_goods'] = cost_of_goods
        totals[tipo]['gross_profit'] = gross_profit
        
        # Gross Profit Margin % = (Gross Profit / Sales) * 100
        if totals[tipo]['sales_total'] > 0:
            gross_profit_margin = (gross_profit / totals[tipo]['sales_total']) * 100
            totals[tipo]['gross_profit_margin'] = round(gross_profit_margin, 2)
        
        # Average Transaction Value = Sales / Number of Transactions
        if totals[tipo]['sales_count'] > 0:
            avg_transaction_value = totals[tipo]['sales_total'] / totals[tipo]['sales_count']
            totals[tipo]['avg_transaction_value'] = round(avg_transaction_value, 2)
        
        # Return Rate % = (Devolution Items / Sales Items) * 100
        if totals[tipo]['items_sold'] > 0:
            return_rate = (totals[tipo]['devolution_items'] / totals[tipo]['items_sold']) * 100
            totals[tipo]['return_rate'] = round(return_rate, 2)
    
    # Calculate combined totals and KPIs
    totals['combined']['sales_count'] = totals['menudeo']['sales_count'] + totals['mayoreo']['sales_count']
    totals['combined']['sales_total'] = totals['menudeo']['sales_total'] + totals['mayoreo']['sales_total']
    totals['combined']['sales_cost'] = totals['menudeo']['sales_cost'] + totals['mayoreo']['sales_cost']
    totals['combined']['items_sold'] = totals['menudeo']['items_sold'] + totals['mayoreo']['items_sold']
    totals['combined']['devolutions_count'] = totals['menudeo']['devolutions_count'] + totals['mayoreo']['devolutions_count']
    totals['combined']['devolutions_total'] = totals['menudeo']['devolutions_total'] + totals['mayoreo']['devolutions_total']
    totals['combined']['devolutions_cost'] = totals['menudeo']['devolutions_cost'] + totals['mayoreo']['devolutions_cost']
    totals['combined']['devolution_items'] = totals['menudeo']['devolution_items'] + totals['mayoreo']['devolution_items']
    
    net_sales = totals['combined']['sales_total'] - totals['combined']['devolutions_total']
    cost_of_goods = totals['combined']['sales_cost'] - totals['combined']['devolutions_cost']
    gross_profit = net_sales - cost_of_goods
    
    totals['combined']['net_sales'] = net_sales
    totals['combined']['cost_of_goods'] = cost_of_goods
    totals['combined']['gross_profit'] = gross_profit
    
    if totals['combined']['sales_total'] > 0:
        gross_profit_margin = (gross_profit / totals['combined']['sales_total']) * 100
        totals['combined']['gross_profit_margin'] = round(gross_profit_margin, 2)
    
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
