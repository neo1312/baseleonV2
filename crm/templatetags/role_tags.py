"""Template tags for role-based access control"""
from django import template
from crm.decorators import user_has_role, get_user_role, get_all_user_roles

register = template.Library()


@register.filter
def has_role(user, role_names):
    """Check if user has any of the specified roles"""
    roles = [r.strip() for r in str(role_names).split(',')]
    return user_has_role(user, *roles)


@register.filter
def user_role(user):
    """Get the primary role of a user"""
    return get_user_role(user)


@register.filter
def user_roles(user):
    """Get all roles for a user"""
    return get_all_user_roles(user)


@register.filter
def all_roles(user):
    """Get all roles comma-separated"""
    roles = get_all_user_roles(user)
    return ', '.join(roles) if roles else 'No Role'
