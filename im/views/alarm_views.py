from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from im.models import AlarmConfig, Alarm, Product
from crm.decorators import role_required


@require_http_methods(["GET"])
@role_required('Admin', 'Manager')
def alarm_list(request):
    """List alarms — scans on every page load for fresh results"""
    check_alarms()

    active_alarms = Alarm.objects.filter(status='active').select_related('product', 'config')
    dismissed_alarms = Alarm.objects.filter(status='skipped').select_related('product', 'config')[:20]

    context = {
        'title': 'Alarms',
        'active_alarms': active_alarms,
        'dismissed_alarms': dismissed_alarms,
        'configs': AlarmConfig.objects.filter(enabled=True),
    }
    return render(request, 'alarm/list.html', context)


@require_http_methods(["POST"])
@role_required('Admin', 'Manager')
def alarm_skip(request, alarm_id):
    """Skip this alarm permanently — user acknowledges this margin is intentional"""
    alarm = get_object_or_404(Alarm, id=alarm_id, status='active')
    alarm.status = 'skipped'
    alarm.resolved_at = timezone.now()
    alarm.resolved_by = str(request.user)
    alarm.save()
    messages.success(request, f'Alarm skipped for {alarm.product.name}')
    return redirect('im:alarm_list')


@require_http_methods(["POST"])
@role_required('Admin', 'Manager')
def alarm_skip_all(request):
    """Skip all active alarms"""
    Alarm.objects.filter(status='active').update(
        status='skipped',
        resolved_at=timezone.now(),
        resolved_by=str(request.user),
    )
    messages.success(request, 'All alarms skipped')
    return redirect('im:alarm_list')


@require_http_methods(["GET", "POST"])
@role_required('Admin')
def alarm_config(request):
    """Manage alarm configurations and thresholds"""
    configs = AlarmConfig.objects.all()

    if request.method == 'POST':
        action = request.POST.get('action')
        config_id = request.POST.get('config_id')
        config = get_object_or_404(AlarmConfig, id=config_id)

        if action == 'toggle':
            config.enabled = not config.enabled
            config.save()
            messages.success(request, f'{config.name} {"enabled" if config.enabled else "disabled"}')
        elif action == 'update_threshold':
            try:
                val = float(request.POST.get('threshold', 0))
                if val < 0:
                    raise ValueError
                config.threshold = val
                config.save()
                messages.success(request, f'{config.name} threshold updated to {val}%')
            except (ValueError, TypeError):
                messages.error(request, 'Invalid threshold value')
        return redirect('im:alarm_config')

    context = {'title': 'Alarm Configuration', 'configs': configs}
    return render(request, 'alarm/config.html', context)


def check_alarms():
    """Scan all products and update alarm state"""
    configs = AlarmConfig.objects.filter(enabled=True)

    for config in configs:
        if config.alarm_type == 'low_margin':
            _check_low_margin(config)


def _check_low_margin(config):
    """Low margin check:
    - Violating → create or update active alarm
    - Fixed → resolve active alarm
    - Skipped → never touch again
    """
    threshold = float(config.threshold)
    products = Product.objects.filter(active=True)
    violating_ids = set()

    for product in products:
        try:
            margen_val = float(product.margen) * 100
            if margen_val < threshold:
                violating_ids.add(product.id)
                _ensure_active_alarm(config, product, margen_val)
        except (ValueError, TypeError):
            pass

    # Resolve active alarms for products now above threshold
    Alarm.objects.filter(
        config=config, status='active'
    ).exclude(product_id__in=violating_ids).update(
        status='resolved',
        resolved_at=timezone.now(),
        resolved_by='system',
    )


def _ensure_active_alarm(config, product, current_value):
    """Create active alarm if none exists. Never touch skipped ones."""
    existing = Alarm.objects.filter(
        config=config, product=product, status='active'
    ).first()

    if existing:
        existing.current_value = current_value
        existing.save()
        return

    # Don't create if already skipped
    skipped = Alarm.objects.filter(
        config=config, product=product, status='skipped'
    ).exists()
    if skipped:
        return

    Alarm.objects.create(
        config=config,
        product=product,
        current_value=current_value,
        threshold=config.threshold,
        status='active',
    )
