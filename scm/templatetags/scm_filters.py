from django import template

register = template.Library()


@register.filter
def get_provider_pv1(product, provider):
    """Get the provider-specific PV1 for a product"""
    if not product or not provider:
        return ''
    return product.get_pv1(provider) or ''


@register.filter
def get_unidad_empaque(product, provider):
    """Get the provider-specific unidad_empaque for a product"""
    if not product or not provider:
        return 1
    return product.get_unidad_empaque(provider)
