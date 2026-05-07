"""
Demand Forecasting System for Lean Inventory Management
Uses industry-standard exponential smoothing and weighted moving average
"""
from django.db.models import Sum, F, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import logging
import math

logger = logging.getLogger(__name__)


def calculate_moving_average(sales_data, periods=30):
    """
    Calculate simple moving average over N periods
    
    Args:
        sales_data: List of tuples (date, quantity) sorted by date
        periods: Number of periods to average
    
    Returns:
        Moving average value
    """
    if not sales_data or len(sales_data) == 0:
        return 0
    
    recent_data = sales_data[-periods:] if len(sales_data) >= periods else sales_data
    if not recent_data:
        return 0
    
    total = sum(qty for _, qty in recent_data)
    return total / len(recent_data)


def calculate_exponential_smoothing(sales_data, alpha=0.3, beta=0.1):
    """
    Calculate exponential smoothing with trend adjustment
    Industry standard for retail demand forecasting
    
    Args:
        sales_data: List of tuples (date, quantity) sorted by date
        alpha: Smoothing coefficient (0.1-0.5, higher = more responsive)
        beta: Trend coefficient (0.01-0.2, higher = stronger trend)
    
    Returns:
        dict with 'forecast', 'trend', 'mape' (Mean Absolute Percentage Error)
    """
    if not sales_data or len(sales_data) < 2:
        return {
            'forecast': sum(qty for _, qty in sales_data) / len(sales_data) if sales_data else 0,
            'trend': 0,
            'confidence': 0
        }
    
    # Initialize
    first_value = sales_data[0][1]
    level = first_value
    trend = (sales_data[1][1] - sales_data[0][1]) / max(1, len(sales_data) - 1)
    
    errors = []
    
    # Run exponential smoothing
    for i, (date, actual) in enumerate(sales_data[1:], 1):
        # Update level
        forecast = level + trend
        if forecast > 0:
            mape_error = abs(actual - forecast) / forecast
            errors.append(mape_error)
        
        # Update parameters
        level_new = alpha * actual + (1 - alpha) * (level + trend)
        trend_new = beta * (level_new - level) + (1 - beta) * trend
        
        level = level_new
        trend = trend_new
    
    # Calculate forecast
    next_forecast = level + trend
    
    # Calculate Mean Absolute Percentage Error
    mape = sum(errors) / len(errors) if errors else 0
    confidence = max(0, 1 - mape)  # Confidence is 1 - MAPE
    
    return {
        'forecast': max(0, next_forecast),
        'trend': trend,
        'confidence': confidence,
        'mape': mape
    }


def get_product_sales_data(product_id, days=90):
    """
    Get daily sales data for a product
    
    Args:
        product_id: Product ID
        days: Number of days of history to retrieve
    
    Returns:
        List of tuples (date, quantity) sorted by date
    """
    from crm.models import saleItem
    from django.db.models import IntegerField
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    sales = saleItem.objects.filter(
        product_id=product_id,
        date_created__gte=cutoff_date
    ).values('date_created').annotate(
        total_qty=Sum('quantity', output_field=IntegerField())
    ).order_by('date_created')
    
    # Group by date (day)
    daily_data = {}
    for sale in sales:
        date_key = sale['date_created'].date() if hasattr(sale['date_created'], 'date') else sale['date_created']
        if date_key not in daily_data:
            daily_data[date_key] = 0
        
        try:
            qty = int(float(sale['total_qty']))
            daily_data[date_key] += qty
        except (ValueError, TypeError):
            pass
    
    # Return as sorted list
    return [(date, qty) for date, qty in sorted(daily_data.items())]


def detect_seasonality(sales_data, window=7):
    """
    Detect seasonal patterns in sales (e.g., weekly patterns)
    
    Args:
        sales_data: List of tuples (date, quantity)
        window: Window size for seasonality (7 for weekly)
    
    Returns:
        dict with seasonal factors for each day
    """
    if len(sales_data) < window * 2:
        # Not enough data for seasonality detection
        return {i: 1.0 for i in range(window)}
    
    # Group by day of week
    seasonal_groups = {i: [] for i in range(window)}
    for date, qty in sales_data:
        day_of_week = date.weekday() if hasattr(date, 'weekday') else date.isoweekday() % 7
        seasonal_groups[day_of_week].append(qty)
    
    # Calculate average for each day
    avg_qty = sum(qty for _, qty in sales_data) / len(sales_data) if sales_data else 1
    
    seasonal_factors = {}
    for day, values in seasonal_groups.items():
        if values:
            day_avg = sum(values) / len(values)
            seasonal_factors[day] = day_avg / avg_qty if avg_qty > 0 else 1.0
        else:
            seasonal_factors[day] = 1.0
    
    return seasonal_factors


def calculate_confidence_interval(forecast, mape, z_score=1.96):
    """
    Calculate confidence interval for forecast
    
    Args:
        forecast: Forecasted value
        mape: Mean Absolute Percentage Error (0-1)
        z_score: Z-score for confidence level (1.96 for 95%)
    
    Returns:
        tuple (lower_bound, upper_bound)
    """
    margin_of_error = forecast * mape * z_score
    return (
        max(0, forecast - margin_of_error),
        forecast + margin_of_error
    )


def forecast_demand(product_id, days_ahead=30, alpha=0.3, beta=0.1, include_seasonality=True):
    """
    Main function to forecast demand for a product
    
    Args:
        product_id: Product ID to forecast
        days_ahead: Number of days to forecast (default 30)
        alpha: Exponential smoothing coefficient
        beta: Trend coefficient
        include_seasonality: Whether to apply seasonal adjustment
    
    Returns:
        dict with forecast data and confidence intervals
    """
    # Get historical data
    sales_data = get_product_sales_data(product_id, days=90)
    
    if not sales_data:
        logger.warning(f'No sales data for product {product_id}, cannot forecast')
        return {
            'product_id': product_id,
            'forecast': 0,
            'days_ahead': days_ahead,
            'confidence': 0,
            'lower_bound': 0,
            'upper_bound': 0,
            'status': 'insufficient_data'
        }
    
    # Calculate base forecast
    result = calculate_exponential_smoothing(sales_data, alpha=alpha, beta=beta)
    base_forecast = result['forecast']
    
    # Apply seasonality if enabled
    if include_seasonality:
        seasonal_factors = detect_seasonality(sales_data)
        # Use average seasonal factor for next period
        avg_seasonal = sum(seasonal_factors.values()) / len(seasonal_factors)
        base_forecast *= avg_seasonal
    
    # Calculate confidence interval
    lower, upper = calculate_confidence_interval(base_forecast, result['mape'])
    
    return {
        'product_id': product_id,
        'forecast': max(0, round(base_forecast)),
        'forecast_daily': max(0, round(base_forecast / days_ahead)),
        'days_ahead': days_ahead,
        'trend': result['trend'],
        'confidence': min(100, round(result['confidence'] * 100)),
        'lower_bound': max(0, round(lower)),
        'upper_bound': round(upper),
        'mape': result['mape'],
        'status': 'success'
    }


def calculate_reorder_point(forecast_daily, lead_time_days=7, safety_stock_multiplier=1.5):
    """
    Calculate reorder point using industry-standard formula
    Reorder Point = (Average Daily Demand × Lead Time) + Safety Stock
    
    Args:
        forecast_daily: Forecasted daily demand
        lead_time_days: Supplier lead time in days
        safety_stock_multiplier: Safety stock multiplier (1.5 = 50% buffer)
    
    Returns:
        Reorder point quantity
    """
    base_reorder = forecast_daily * lead_time_days
    safety_stock = forecast_daily * lead_time_days * (safety_stock_multiplier - 1)
    return int(base_reorder + safety_stock)


def calculate_economic_order_quantity(
    annual_demand,
    order_cost_per_unit=100,
    holding_cost_per_unit_per_year=5
):
    """
    Calculate Economic Order Quantity (EOQ)
    EOQ = sqrt((2 × D × S) / H)
    
    Args:
        annual_demand: Annual demand in units
        order_cost_per_unit: Cost per order
        holding_cost_per_unit_per_year: Annual holding cost per unit
    
    Returns:
        Economic order quantity
    """
    if holding_cost_per_unit_per_year <= 0:
        return 0
    
    eoq = math.sqrt(
        (2 * annual_demand * order_cost_per_unit) / holding_cost_per_unit_per_year
    )
    return int(eoq)
