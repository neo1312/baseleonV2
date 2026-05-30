from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count, Q

from datetime import date, timedelta
from decimal import Decimal, DecimalException

from im.models import AlarmConfig, Alarm, Product, InventoryAudit
from crm.decorators import role_required


@require_http_methods(["GET"])
@role_required('Admin', 'Manager')
def alarm_list(request):
    """List alarms — scans on every page load for fresh results"""
    check_alarms()

    alarm_type = request.GET.get('type', '')

    active_qs = Alarm.objects.filter(status='active').select_related('product', 'config')
    dismissed_qs = Alarm.objects.filter(status='skipped').select_related('product', 'config')

    if alarm_type:
        active_qs = active_qs.filter(config__alarm_type=alarm_type)
        dismissed_qs = dismissed_qs.filter(config__alarm_type=alarm_type)

    active_alarms = active_qs
    dismissed_alarms = dismissed_qs[:20]

    all_types = AlarmConfig.objects.filter(enabled=True).values_list('alarm_type', 'name')

    context = {
        'title': 'Alarms',
        'active_alarms': active_alarms,
        'dismissed_alarms': dismissed_alarms,
        'configs': AlarmConfig.objects.filter(enabled=True),
        'all_types': all_types,
        'current_type': alarm_type,
    }
    return render(request, 'alarm/list.html', context)


@require_http_methods(["POST"])
@role_required('Admin', 'Manager')
def alarm_skip(request, alarm_id):
    """Skip this alarm permanently — user provides reason"""
    alarm = get_object_or_404(Alarm, id=alarm_id, status='active')
    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'Please provide a reason for skipping')
        return redirect('im:alarm_list')
    alarm.status = 'skipped'
    alarm.notes = reason
    alarm.resolved_at = timezone.now()
    alarm.resolved_by = str(request.user)
    alarm.save()
    product_name = alarm.product.name if alarm.product else 'System'
    messages.success(request, f'Alarm skipped for {product_name}')
    return redirect('im:alarm_list')


@require_http_methods(["POST"])
@role_required('Admin', 'Manager')
def alarm_skip_all(request):
    """Skip all active alarms with a reason"""
    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'Please provide a reason for skipping all alarms')
        return redirect('im:alarm_list')
    Alarm.objects.filter(status='active').update(
        status='skipped',
        notes=reason,
        resolved_at=timezone.now(),
        resolved_by=str(request.user),
    )
    messages.success(request, 'All alarms skipped')
    return redirect('im:alarm_list')


@require_http_methods(["POST"])
@role_required('Admin', 'Manager')
def alarm_delete(request, alarm_id):
    """Permanently delete a skipped alarm"""
    alarm = get_object_or_404(Alarm, id=alarm_id, status='skipped')
    alarm.delete()
    messages.success(request, 'Alarm deleted permanently')
    return redirect('im:alarm_list')


@require_http_methods(["POST"])
@role_required('Admin', 'Manager')
def alarm_adjust(request, alarm_id):
    """Adjust margin or set manual price to resolve a low_margin alarm"""
    alarm = get_object_or_404(Alarm, id=alarm_id, status='active')
    if not alarm.product:
        messages.error(request, 'Cannot adjust — no product linked to this alarm')
        return redirect('im:alarm_list')

    action = request.POST.get('action')
    product = alarm.product

    if action == 'set_margin':
        try:
            new_margin = float(request.POST.get('new_margin', 0))
            if new_margin < 0:
                raise ValueError
            product.margen = str(new_margin / 100)
            product.pricing_mode = 'margin'
            product.precio_manual = None
            product.save()
            alarm.status = 'resolved'
            alarm.resolved_at = timezone.now()
            alarm.resolved_by = str(request.user)
            alarm.save()
            messages.success(request, f'{product.name} margin updated to {new_margin}%')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid margin value')

    elif action == 'set_price':
        try:
            new_price = Decimal(str(request.POST.get('new_price', 0)))
            if new_price <= 0:
                raise ValueError
            product.precio_manual = new_price
            product.pricing_mode = 'price'
            product.save()
            alarm.status = 'resolved'
            alarm.resolved_at = timezone.now()
            alarm.resolved_by = str(request.user)
            alarm.save()
            messages.success(request, f'{product.name} price set to ${new_price:.2f}')
        except (ValueError, TypeError, DecimalException):
            messages.error(request, 'Invalid price value')

    elif action == 'set_promotion':
        product.on_promotion = True
        product.save()
        alarm.status = 'resolved'
        alarm.resolved_at = timezone.now()
        alarm.resolved_by = str(request.user)
        alarm.notes = 'Marked as promotion'
        alarm.save()
        messages.success(request, f'{product.name} marked as on promotion — alarm suppressed')

    else:
        messages.error(request, 'Invalid action')

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


DEFAULT_ALARM_CONFIGS = {
    'low_margin': {
        'name': 'Low Margin',
        'threshold': 15.0,
    },
    'missing_random_audit': {
        'name': 'Missing Random Audit',
        'threshold': 0.0,
    },
}


def _ensure_default_configs():
    """Create default AlarmConfig entries if they don't exist."""
    for alarm_type, defaults in DEFAULT_ALARM_CONFIGS.items():
        AlarmConfig.objects.get_or_create(
            alarm_type=alarm_type,
            defaults=defaults,
        )


def check_alarms():
    """Scan all products and update alarm state"""
    _ensure_default_configs()
    configs = AlarmConfig.objects.filter(enabled=True)

    for config in configs:
        if config.alarm_type == 'low_margin':
            _check_low_margin(config)
        elif config.alarm_type == 'missing_random_audit':
            _check_missing_random_audit(config)


def _check_low_margin(config):
    """Low margin check — only active products with available stock.
    - Violating → create or update active alarm
    - Fixed → resolve active alarm
    - Skipped → never touch again
    """
    threshold = float(config.threshold)
    products = Product.objects.filter(active=True).annotate(
        ready_count=Count('inventoryunit_set', filter=Q(status='ready_to_sale'))
    ).filter(ready_count__gt=0)
    violating_ids = set()

    for product in products:
        if product.on_promotion:
            continue
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


def _check_missing_random_audit(config):
    """Check if a random audit was completed today. Create alarm if not."""
    today = date.today()
    audit_done = InventoryAudit.objects.filter(
        audit_type__in=['random', 'random_custom'],
        status='completed',
        audit_date=today,
    ).exists()

    if audit_done:
        # Resolve any active alarm for this config
        Alarm.objects.filter(config=config, status='active').update(
            status='resolved',
            resolved_at=timezone.now(),
            resolved_by='system',
        )
    else:
        # Create or keep active alarm (no product for this type)
        existing = Alarm.objects.filter(config=config, status='active').first()
        if not existing:
            skipped = Alarm.objects.filter(config=config, status='skipped').exists()
            if not skipped:
                Alarm.objects.create(
                    config=config,
                    product=None,
                    current_value=0,
                    threshold=config.threshold,
                    status='active',
                    notes='No random audit completed today',
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
