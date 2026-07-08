"""Role-based decorators and utilities for access control"""
from functools import wraps
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.contrib import messages

ROLE_ALIASES = {
    'admin': 'Admin',
    'manager': 'Manager',
    'cashier': 'Cashier',
    'cajero': 'Cashier',
    'auditor': 'Auditor',
    'buyer': 'Buyer',
    'wholesalebuyer': 'WholesaleBuyer',
    'wholesale_buyer': 'WholesaleBuyer',
}


def _canonical_roles(role_names):
    """Map a list of role names to their canonical form (case-insensitive + aliases)"""
    result = set()
    for r in role_names:
        result.add(ROLE_ALIASES.get(r.lower(), r))
    return result


def role_required(*role_names):
    """
    Decorator to check if user belongs to any of the specified roles.
    Case-insensitive and supports aliases (e.g. 'cajero' matches 'Cashier').
    """
    required = _canonical_roles(role_names)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_authenticated:
                user_roles = _canonical_roles(
                    request.user.groups.values_list('name', flat=True)
                )
                if user_roles.intersection(required):
                    return view_func(request, *args, **kwargs)
                else:
                    messages.error(request, 'You do not have permission to access this page.')
                    return redirect('/')
            else:
                next_url = request.path
                if request.GET:
                    next_url = f"{request.path}?{request.GET.urlencode()}"
                return redirect(f'/login/?next={next_url}')

        return wrapper
    return decorator


def user_has_role(user, *role_names):
    """
    Check if user belongs to any of the specified roles.
    Case-insensitive and supports aliases.
    """
    if not user.is_authenticated:
        return False

    required = _canonical_roles(role_names)
    user_roles = _canonical_roles(user.groups.values_list('name', flat=True))
    return bool(user_roles.intersection(required))


def get_user_role(user):
    """Get the primary role of a user (canonical form)"""
    if not user.is_authenticated:
        return None

    group = user.groups.first()
    if group:
        canon = _canonical_roles([group.name])
        return next(iter(canon))
    return None


def get_all_user_roles(user):
    """Get all roles for a user (canonical form)"""
    if not user.is_authenticated:
        return []

    return list(_canonical_roles(user.groups.values_list('name', flat=True)))
