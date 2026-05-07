"""
ABC Inventory Classification System
Uses Pareto principle (80/20) to classify products based on sales revenue
"""
from django.db.models import Sum, F, Q, DecimalField
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def get_abc_config():
    """Get ABC configuration settings"""
    from im.models import ABCConfiguration
    config, created = ABCConfiguration.objects.get_or_create(id=1)
    return config


def get_sales_revenue_data(days=30):
    """
    Get sales revenue data for products in the specified time period
    Returns: dict of {product_id: total_revenue}
    """
    from crm.models import saleItem
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Query sales items from the last N days
    sales_data = saleItem.objects.filter(
        date_created__gte=cutoff_date,
        product__isnull=False
    ).values('product_id').annotate(
        total_revenue=Sum(
            F('price') * F('quantity'),
            output_field=DecimalField()
        ),
        units_sold=Sum(F('quantity'))
    )
    
    return {item['product_id']: {
        'revenue': item['total_revenue'] or Decimal('0.00'),
        'units': item['units_sold'] or 0
    } for item in sales_data}


def calculate_abc_classification(revenue_data, pareto_a=80, pareto_b=95):
    """
    Calculate ABC classification using Pareto principle
    
    Args:
        revenue_data: dict of {product_id: {'revenue': Decimal, 'units': int}}
        pareto_a: Threshold for A classification (default 80%)
        pareto_b: Threshold for B classification (default 95%)
    
    Returns:
        dict of {product_id: classification}
    """
    if not revenue_data:
        return {}
    
    # Sort products by revenue (descending)
    sorted_products = sorted(
        revenue_data.items(),
        key=lambda x: x[1]['revenue'],
        reverse=True
    )
    
    # Calculate total revenue
    total_revenue = sum(item[1]['revenue'] for item in sorted_products)
    
    if total_revenue == 0:
        return {product_id: 'unclassified' for product_id, _ in sorted_products}
    
    # Assign classifications
    classifications = {}
    cumulative_revenue = Decimal('0.00')
    cumulative_percentage = Decimal('0.00')
    
    for product_id, data in sorted_products:
        cumulative_revenue += data['revenue']
        cumulative_percentage = (cumulative_revenue / total_revenue) * 100
        
        if cumulative_percentage <= Decimal(str(pareto_a)):
            classifications[product_id] = ('A', cumulative_percentage)
        elif cumulative_percentage <= Decimal(str(pareto_b)):
            classifications[product_id] = ('B', cumulative_percentage)
        else:
            classifications[product_id] = ('C', cumulative_percentage)
    
    return classifications


def update_product_abc_metrics():
    """
    Update ProductABCMetrics table with current ABC classifications
    Recalculates based on configuration settings
    """
    from im.models import ProductABCMetrics, Product
    
    config = get_abc_config()
    revenue_data = get_sales_revenue_data(days=config.time_period_days)
    
    classifications = calculate_abc_classification(
        revenue_data,
        pareto_a=float(config.pareto_a_threshold),
        pareto_b=float(config.pareto_b_threshold)
    )
    
    # Update metrics for all products with sales data
    for product_id, class_tuple in classifications.items():
        if isinstance(class_tuple, tuple):
            classification, cum_percentage = class_tuple
        else:
            classification = class_tuple
            cum_percentage = Decimal('0.00')
        
        metrics, created = ProductABCMetrics.objects.get_or_create(
            product_id=product_id
        )
        
        metrics.abc_classification = classification
        metrics.last_30_days_revenue = revenue_data[product_id]['revenue']
        metrics.last_30_days_units_sold = revenue_data[product_id]['units']
        metrics.cumulative_revenue_percentage = cum_percentage
        metrics.save()
    
    # Mark products with no recent sales as unclassified
    all_products = set(Product.objects.values_list('id', flat=True))
    products_with_sales = set(classifications.keys())
    no_sales_products = all_products - products_with_sales
    
    for product_id in no_sales_products:
        metrics, created = ProductABCMetrics.objects.get_or_create(
            product_id=product_id
        )
        metrics.abc_classification = 'unclassified'
        metrics.last_30_days_revenue = Decimal('0.00')
        metrics.last_30_days_units_sold = 0
        metrics.cumulative_revenue_percentage = Decimal('0.00')
        metrics.save()
    
    # Update last recalculation time
    config.last_recalculation = timezone.now()
    config.save()
    
    logger.info(f'ABC metrics updated: {len(classifications)} products classified')
    return len(classifications)


def update_inventory_units_abc():
    """
    Update InventoryUnit ABC classifications based on their products' classifications
    """
    from im.models import InventoryUnit, ProductABCMetrics
    
    # Get all products with metrics
    metrics = ProductABCMetrics.objects.filter(
        abc_classification__in=['A', 'B', 'C']
    )
    
    update_count = 0
    for metric in metrics:
        # Update all inventory units for this product that have different classification
        units_to_update = InventoryUnit.objects.filter(
            product_id=metric.product_id
        ).exclude(
            abc_classification=metric.abc_classification
        )
        
        updated = units_to_update.update(abc_classification=metric.abc_classification)
        update_count += updated
    
    logger.info(f'Updated {update_count} inventory units with ABC classifications')
    return update_count


def recalculate_abc():
    """
    Main function to recalculate ABC classification system
    Called after sales/devolutions or on schedule
    """
    logger.info('Starting ABC recalculation...')
    
    # Update ProductABCMetrics
    products_updated = update_product_abc_metrics()
    
    # Update InventoryUnit classifications
    units_updated = update_inventory_units_abc()
    
    logger.info(f'ABC recalculation complete: {products_updated} products, {units_updated} units updated')
    return {
        'products': products_updated,
        'units': units_updated
    }
