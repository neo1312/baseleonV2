from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from crm.utils import get_dashboard_for_user, get_menu_for_user

def home(request):
    """Home page - main dashboard"""
    if not request.user.is_authenticated:
        return redirect('/login/')
    
    dashboard = get_dashboard_for_user(request.user)
    menu = get_menu_for_user(request.user)
    
    context = {
        'dashboard': dashboard,
        'menu': menu,
    }
    return render(request, 'index.html', context)

@csrf_exempt
def user_login(request):
    """User login page"""
    if request.user.is_authenticated:
        return redirect('/')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            error = 'Usuario o contraseña incorrectos'
            return render(request, 'login.html', {'error': error})
    
    return render(request, 'login.html', {})

@csrf_exempt
def user_logout(request):
    """User logout"""
    logout(request)
    return redirect('/login/')
