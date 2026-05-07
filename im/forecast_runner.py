"""
Demand Forecast Calculator and Runner
"""
from im.models import Product, DemandForecast, ForecastConfiguration
from im.demand_forecast import (
    forecast_demand,
    calculate_reorder_point,
    calculate_economic_order_quantity
)
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def recalculate_all_forecasts():
    """
    Recalculate demand forecasts for all active products
    
    Returns:
        dict with {'updated': count, 'errors': count}
    """
    config = ForecastConfiguration.objects.first()
    if not config:
        config = ForecastConfiguration.objects.create()
    
    products = Product.objects.filter(active=True)
    updated_count = 0
    error_count = 0
    
    for product in products:
        try:
            result = forecast_demand(
                product.id,
                days_ahead=config.forecast_horizon_days,
                alpha=float(config.alpha),
                beta=float(config.beta),
                include_seasonality=config.include_seasonality
            )
            
            # Calculate recommendations
            daily_forecast = float(result['forecast'] / config.forecast_horizon_days)
            reorder_point = calculate_reorder_point(
                daily_forecast,
                lead_time_days=config.supplier_lead_time_days,
                safety_stock_multiplier=float(config.safety_stock_multiplier)
            )
            
            # Calculate EOQ (simplified: annual_demand = daily * 365)
            annual_demand = daily_forecast * 365
            eoq = calculate_economic_order_quantity(annual_demand)
            
            # Update or create forecast
            forecast, created = DemandForecast.objects.update_or_create(
                product_id=product.id,
                defaults={
                    'forecast_daily': Decimal(str(daily_forecast)),
                    'forecast_30days': Decimal(str(result['forecast'])),
                    'confidence_level': result['confidence'],
                    'lower_bound': Decimal(str(result['lower_bound'])),
                    'upper_bound': Decimal(str(result['upper_bound'])),
                    'trend': Decimal(str(result['trend'])),
                    'mape': Decimal(str(result['mape'])),
                    'reorder_point': reorder_point,
                    'eoq': eoq,
                    'last_sales_data_count': 0,  # Could track actual data points if needed
                }
            )
            
            updated_count += 1
            logger.info(f'Updated forecast for product {product.id}: daily={daily_forecast:.2f}, confidence={result["confidence"]}%')
        
        except Exception as e:
            error_count += 1
            logger.error(f'Error calculating forecast for product {product.id}: {str(e)}')
    
    # Update config timestamp
    config.last_recalculation = timezone.now()
    config.save()
    
    logger.info(f'Forecast recalculation complete: {updated_count} updated, {error_count} errors')
    return {
        'updated': updated_count,
        'errors': error_count
    }


def get_forecast_summary():
    """
    Get summary of all forecasts for dashboard
    
    Returns:
        dict with summary statistics
    """
    forecasts = DemandForecast.objects.all()
    
    if not forecasts.exists():
        return {
            'total_products': 0,
            'avg_forecast': 0,
            'high_confidence': 0,
            'low_confidence': 0,
            'high_demand': 0
        }
    
    total_forecast = sum(f.forecast_30days for f in forecasts)
    avg_forecast = total_forecast / forecasts.count() if forecasts.count() > 0 else 0
    high_confidence = forecasts.filter(confidence_level__gte=80).count()
    low_confidence = forecasts.filter(confidence_level__lt=50).count()
    high_demand = forecasts.filter(forecast_daily__gte=avg_forecast).count()
    
    return {
        'total_products': forecasts.count(),
        'avg_forecast_30d': float(avg_forecast),
        'high_confidence_count': high_confidence,
        'low_confidence_count': low_confidence,
        'high_demand_count': high_demand,
        'last_update': ForecastConfiguration.objects.first().last_recalculation if ForecastConfiguration.objects.first() else None
    }
