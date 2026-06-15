from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone

from crm.models import CashRegisterSession, CashCount, CajaConfig, Sale
from crm.decorators import role_required


@login_required
@role_required('Admin', 'Cashier')
def session_list(request):
    sessions = CashRegisterSession.objects.all().select_related('cashier', 'cash_count')
    open_session = sessions.filter(status='open').first()
    for s in sessions:
        cc = getattr(s, 'cash_count', None)
        if cc:
            s.net_expected = (cc.expected_cash_total + cc.expected_card_total + cc.expected_check_total) - s.opening_balance
            s.net_delivered = cc.total_counted - s.opening_balance
        else:
            s.net_expected = None
            s.net_delivered = None
    context = {
        'title': 'Cierre de Caja',
        'sessions': sessions,
        'open_session': open_session,
    }
    return render(request, 'crm/cash_register/session_list.html', context)


@login_required
@role_required('Admin', 'Cashier')
def session_open(request):
    if request.method == 'POST':
        opening_balance = request.POST.get('opening_balance', '0')
        try:
            opening_balance = Decimal(str(opening_balance))
        except:
            opening_balance = Decimal('0')
        CashRegisterSession.objects.create(
            cashier=request.user,
            opening_balance=opening_balance,
            opened_at=timezone.localtime(timezone.now()),
            status='open',
        )
        return redirect('crm:cash_session_detail')
    context = {'title': 'Abrir Caja'}
    return render(request, 'crm/cash_register/session_open.html', context)


@login_required
@role_required('Admin', 'Cashier')
def session_detail(request):
    session = CashRegisterSession.objects.filter(status='open').select_related('cashier').first()
    if not session:
        return redirect('crm:cash_session_list')

    expected_cash = session.expected_cash_total()
    expected_card = session.expected_card_total()
    expected_check = session.expected_check_total()
    total_expected = expected_cash + expected_card + expected_check

    cutoff_config = CajaConfig.get()
    now = timezone.localtime(timezone.now())
    weekday = now.weekday()  # Lun=0, Dom=6

    # Determine cutoff and next day label
    if weekday == 5:  # Sábado
        cutoff_today = cutoff_config.cutoff_time_saturday
        next_day_label = 'Lunes'
    elif weekday == 6:  # Domingo
        cutoff_today = None
        next_day_label = 'Lunes'
    else:
        cutoff_today = cutoff_config.cutoff_time
        next_day_label = 'mañana'

    # Find sales made after today's cutoff (they belong to next session)
    post_cutoff_sales = []
    post_cutoff_total = Decimal('0')
    if cutoff_today and now.time() > cutoff_today:
        cutoff_dt = now.replace(hour=cutoff_today.hour, minute=cutoff_today.minute, second=0, microsecond=0)
        post_cutoff_sales = list(Sale.objects.filter(
            date_created__gte=cutoff_dt,
            date_created__lt=now,
            status='completed',
        ))
        if post_cutoff_sales:
            post_cutoff_total = sum(s.total_amount for s in post_cutoff_sales)

    if request.method == 'POST':
        if weekday == 6:  # Domingo → todo a lunes
            effective_date = now.date() + timedelta(days=1)
        elif weekday == 5:  # Sábado
            if now.time() > cutoff_config.cutoff_time_saturday:
                effective_date = now.date() + timedelta(days=2)
            else:
                effective_date = now.date()
        else:  # Lunes-Viernes
            if now.time() > cutoff_config.cutoff_time:
                effective_date = now.date() + timedelta(days=1)
            else:
                effective_date = now.date()

        session.closed_at = now
        session.status = 'closed'
        session.effective_date = effective_date

        count = CashCount(session=session)
        for field, _ in CashCount.DENOMINATIONS:
            val = request.POST.get(field, '0')
            try:
                setattr(count, field, int(val))
            except (ValueError, TypeError):
                setattr(count, field, 0)

        card_val = request.POST.get('counted_card_total', '0')
        check_val = request.POST.get('counted_check_total', '0')
        try:
            count.counted_card_total = Decimal(str(card_val))
        except:
            count.counted_card_total = Decimal('0')
        try:
            count.counted_check_total = Decimal(str(check_val))
        except:
            count.counted_check_total = Decimal('0')

        count.expected_cash_total = expected_cash
        count.expected_card_total = expected_card
        count.expected_check_total = expected_check
        count.notes = request.POST.get('notes', '')

        count.save()
        session.save()

        return redirect('crm:cash_session_list')

    context = {
        'title': 'Arqueo de Caja',
        'session': session,
        'expected_cash': float(expected_cash),
        'expected_card': float(expected_card),
        'expected_check': float(expected_check),
        'total_expected': float(total_expected),
        'DENOMINATIONS': CashCount.DENOMINATIONS,
        'post_cutoff_sales': post_cutoff_sales,
        'post_cutoff_total': float(post_cutoff_total),
        'post_cutoff_count': len(post_cutoff_sales),
        'next_day_label': next_day_label,
        'cutoff_today': cutoff_today,
    }
    return render(request, 'crm/cash_register/session_detail.html', context)
