from django import template

register = template.Library()


@register.filter
def get_provider_pv1(product, provider):
    """Get the provider-specific PV1 for a product"""
    if not product or not provider:
        return ''
    return product.get_pv1(provider) or ''
