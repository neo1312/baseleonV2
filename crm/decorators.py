"""Role-based decorators and utilities for access control"""
from functools import wraps
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*role_names):
    """
    Decorator to check if user belongs to any of the specified roles.
    
    Usage:
        @role_required('Admin', 'Manager')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_authenticated:
                user_roles = set(request.user.groups.values_list('name', flat=True))
                if user_roles.intersection(set(role_names)):
                    return view_func(request, *args, **kwargs)
            
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('/')
        
        return wrapper
    return decorator


def user_has_role(user, *role_names):
    """
    Check if user belongs to any of the specified roles.
    
    Usage:
        if user_has_role(request.user, 'Admin', 'Manager'):
            ...
    """
    if not user.is_authenticated:
        return False
    
    user_roles = set(user.groups.values_list('name', flat=True))
    return bool(user_roles.intersection(set(role_names)))


def get_user_role(user):
    """Get the primary role of a user (first group)"""
    if not user.is_authenticated:
        return None
    
    group = user.groups.first()
    return group.name if group else None


def get_all_user_roles(user):
    """Get all roles for a user"""
    if not user.is_authenticated:
        return []
    
    return list(user.groups.values_list('name', flat=True))
