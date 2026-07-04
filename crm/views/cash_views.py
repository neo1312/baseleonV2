from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone

from crm.models import CashRegisterSession, CashCount, Sale, Devolution
from crm.decorators import role_required


@login_required
@role_required('Admin', 'Cashier')
def session_list(request):
    sessions = CashRegisterSession.objects.all().select_related('cashier', 'cash_count')
    open_session = sessions.filter(status='open').first()

    for s in sessions:
        cc = getattr(s, 'cash_count', None)
        if cc:
            s.net_expected = cc.expected_cash_total + cc.expected_card_total + cc.expected_check_total
            s.net_delivered = cc.total_counted
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
    if CashRegisterSession.objects.filter(status='open').exists():
        return redirect('crm:cash_session_detail')

    now = timezone.localtime(timezone.now())

    carryover = Decimal('0')
    prev_session = CashRegisterSession.objects.filter(status='closed').order_by('-closed_at').first()
    if prev_session:
        cash_closed = Sale.objects.filter(
            date_created__gt=prev_session.closed_at,
            date_created__lt=now,
            payment_method='cash',
            status='completed',
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        carryover = Decimal(str(cash_closed))
    else:
        cash_closed = Sale.objects.filter(
            status='completed',
            payment_method='cash',
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        carryover = Decimal(str(cash_closed))

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

    now = timezone.localtime(timezone.now())

    cash_sales = Sale.objects.filter(
        date_created__gte=session.opened_at,
        date_created__lt=now,
        payment_method='cash',
        status='completed',
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    card_sales = Sale.objects.filter(
        date_created__gte=session.opened_at,
        date_created__lt=now,
        payment_method='card',
        status='completed',
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    check_sales = Sale.objects.filter(
        date_created__gte=session.opened_at,
        date_created__lt=now,
        payment_method='check',
        status='completed',
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    dev_total = sum(
        d.get_cart_total for d in Devolution.objects.filter(
            date_created__gte=session.opened_at,
            date_created__lt=now,
        )
    )

    expected_cash = session.carryover_amount + Decimal(str(cash_sales)) - Decimal(str(dev_total))
    expected_card = Decimal(str(card_sales))
    expected_check = Decimal(str(check_sales))
    total_expected = expected_cash + expected_card + expected_check

    if request.method == 'POST':
        session.closed_at = now
        session.status = 'closed'
        session.effective_date = now.date()
        session.post_cutoff_cash = Decimal('0')

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
        'carryover': float(session.carryover_amount),
    }
    return render(request, 'crm/cash_register/session_detail.html', context)
