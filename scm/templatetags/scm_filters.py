from decimal import Decimal
from django import template

register = template.Library()


@register.filter
def get_provider_pv1(product, provider):
    if not product or not provider:
        return ''
    return product.get_pv1(provider) or ''


@register.filter
def get_unidad_empaque(product, provider):
    if not product or not provider:
        return 1
    return product.get_unidad_empaque(provider)


@register.filter
def div(value, divisor):
    try:
        return Decimal(str(value)) / Decimal(str(divisor))
    except (ValueError, TypeError, ZeroDivisionError):
        return Decimal('0')


@register.filter
def sub(value, subtractor):
    try:
        return Decimal(str(value)) - Decimal(str(subtractor))
    except (ValueError, TypeError):
        return Decimal('0')
