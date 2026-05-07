"""Context processors for global template variables"""
from crm.utils import get_dashboard_for_user, get_menu_for_user
from crm.decorators import get_user_role, get_all_user_roles


def user_dashboard_context(request):
    """Add user dashboard and menu to all templates"""
    context = {}
    
    if request.user.is_authenticated:
        context['user_dashboard'] = get_dashboard_for_user(request.user)
        context['user_menu'] = get_menu_for_user(request.user)
        context['user_role'] = get_user_role(request.user)
        context['user_roles'] = get_all_user_roles(request.user)
    
    return context
