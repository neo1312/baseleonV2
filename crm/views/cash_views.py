from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone

from crm.models import CashRegisterSession, CashCount, CajaConfig, Sale, Devolution
from crm.decorators import role_required


def _get_cutoff_info(now, cutoff_config):
    weekday = now.weekday()
    cutoff_today = cutoff_config.get_cutoff_for_weekday(weekday)
    cutoff_dt = None
    next_day_label = 'mañana'

    if weekday == 5:
        next_day_label = 'Lunes'
    elif weekday == 6:
        next_day_label = 'Lunes'
        cutoff_today = None

    if cutoff_today:
        cutoff_dt = now.replace(hour=cutoff_today.hour, minute=cutoff_today.minute, second=0, microsecond=0)

    return cutoff_today, cutoff_dt, next_day_label


def _get_effective_date(now, cutoff_config, is_after_cutoff):
    weekday = now.weekday()
    if weekday == 6:
        return now.date() + timedelta(days=1)
    elif weekday == 5:
        if is_after_cutoff:
            return now.date() + timedelta(days=2)
        return now.date()
    else:
        if is_after_cutoff:
            return now.date() + timedelta(days=1)
        return now.date()


@login_required
@role_required('Admin', 'Cashier')
def session_list(request):
    sessions = CashRegisterSession.objects.all().select_related('cashier', 'cash_count')
    open_session = sessions.filter(status='open').first()
    cutoff_config = CajaConfig.get()

    for s in sessions:
        cc = getattr(s, 'cash_count', None)
        if cc:
            s.net_expected = cc.expected_cash_total + cc.expected_card_total + cc.expected_check_total
            s.net_delivered = cc.total_counted
        else:
            s.net_expected = None
            s.net_delivered = None

        if s.status == 'closed' and not s.post_cutoff_cash and s.closed_at and s.opened_at:
            closed_local = timezone.localtime(s.closed_at)
            weekday = closed_local.weekday()
            if weekday != 6:
                cutoff_time = cutoff_config.get_cutoff_for_weekday(weekday)
                if cutoff_time and closed_local.time() > cutoff_time:
                    cutoff_dt = closed_local.replace(
                        hour=cutoff_time.hour, minute=cutoff_time.minute, second=0, microsecond=0
                    )
                    fallback = Sale.objects.filter(
                        date_created__gte=cutoff_dt,
                        date_created__lt=s.closed_at,
                        payment_method='cash',
                        status='completed',
                    ).aggregate(total=Sum('total_amount'))['total'] or 0
                    if not s.post_cutoff_cash:
                        s.post_cutoff_cash = fallback

    context = {
        'title': 'Cierre de Caja',
        'sessions': sessions,
        'open_session': open_session,
    }
    return render(request, 'crm/cash_register/session_list.html', context)


@login_required
@role_required('Admin', 'Cashier')
def session_open(request):
    if CashRegisterSession.objects.filter(status='open').exists():
        return redirect('crm:cash_session_detail')

    cutoff_config = CajaConfig.get()

    carryover = Decimal('0')
    prev_session = CashRegisterSession.objects.filter(status='closed').order_by('-closed_at').first()
    if prev_session:
        carryover = prev_session.post_cutoff_cash
        if not carryover and prev_session.closed_at:
            closed_local = timezone.localtime(prev_session.closed_at)
            weekday = closed_local.weekday()
            cutoff_time = cutoff_config.get_cutoff_for_weekday(weekday)
            if cutoff_time and closed_local.time() > cutoff_time:
                cutoff_dt = closed_local.replace(
                    hour=cutoff_time.hour, minute=cutoff_time.minute, second=0, microsecond=0
                )
                carryover = Sale.objects.filter(
                    date_created__gte=cutoff_dt,
                    date_created__lt=prev_session.closed_at,
                    payment_method='cash',
                    status='completed',
                ).aggregate(total=Sum('total_amount'))['total'] or 0

    if request.method == 'POST':
        opening_balance = request.POST.get('opening_balance', '0')
        try:
            opening_balance = Decimal(str(opening_balance))
        except:
            opening_balance = Decimal('0')
        CashRegisterSession.objects.create(
            cashier=request.user,
            opening_balance=opening_balance,
            carryover_amount=carryover,
            opened_at=timezone.localtime(timezone.now()),
            status='open',
        )
        return redirect('crm:cash_session_detail')

    context = {
        'title': 'Abrir Caja',
        'carryover': float(carryover),
        'suggested_total': float(Decimal('1000') + carryover),
    }
    return render(request, 'crm/cash_register/session_open.html', context)


@login_required
@role_required('Admin', 'Cashier')
def session_detail(request):
    session = CashRegisterSession.objects.filter(status='open').select_related('cashier').first()
    if not session:
        return redirect('crm:cash_session_list')

    cutoff_config = CajaConfig.get()
    now = timezone.localtime(timezone.now())
    cutoff_today, cutoff_dt, next_day_label = _get_cutoff_info(now, cutoff_config)

    pre_cutoff_end = now
    is_after_cutoff = False
    if cutoff_today and now.time() > cutoff_today:
        pre_cutoff_end = cutoff_dt
        is_after_cutoff = True

    cash_sales = Sale.objects.filter(
        date_created__gte=session.opened_at,
        date_created__lt=pre_cutoff_end,
        payment_method='cash',
        status='completed',
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    card_sales = Sale.objects.filter(
        date_created__gte=session.opened_at,
        date_created__lt=pre_cutoff_end,
        payment_method='card',
        status='completed',
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    check_sales = Sale.objects.filter(
        date_created__gte=session.opened_at,
        date_created__lt=pre_cutoff_end,
        payment_method='check',
        status='completed',
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    dev_total = sum(
        d.get_cart_total for d in Devolution.objects.filter(
            date_created__gte=session.opened_at,
            date_created__lt=pre_cutoff_end,
        )
    )

    expected_cash = session.carryover_amount + Decimal(str(cash_sales)) - Decimal(str(dev_total))
    expected_card = Decimal(str(card_sales))
    expected_check = Decimal(str(check_sales))
    total_expected = expected_cash + expected_card + expected_check

    post_cutoff_sales = []
    post_cutoff_total = Decimal('0')
    post_cutoff_cash = Decimal('0')
    if is_after_cutoff and cutoff_dt:
        post_cutoff_sales = list(Sale.objects.filter(
            date_created__gte=cutoff_dt,
            date_created__lt=now,
            status='completed',
        ))
        if post_cutoff_sales:
            post_cutoff_total = sum(s.total_amount for s in post_cutoff_sales)
            post_cutoff_cash = Sale.objects.filter(
                date_created__gte=cutoff_dt,
                date_created__lt=now,
                payment_method='cash',
                status='completed',
            ).aggregate(total=Sum('total_amount'))['total'] or 0

    if request.method == 'POST':
        effective_date = _get_effective_date(now, cutoff_config, is_after_cutoff)

        session.closed_at = now
        session.status = 'closed'
        session.effective_date = effective_date
        session.post_cutoff_cash = post_cutoff_cash

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
        'post_cutoff_cash': float(post_cutoff_cash),
        'post_cutoff_count': len(post_cutoff_sales),
        'next_day_label': next_day_label,
        'cutoff_today': cutoff_today,
        'carryover': float(session.carryover_amount),
    }
    return render(request, 'crm/cash_register/session_detail.html', context)
