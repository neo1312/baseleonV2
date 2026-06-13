from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone

from crm.models import CashRegisterSession, CashCount, CajaConfig
from crm.decorators import role_required


@login_required
@role_required('Admin', 'Cashier')
def session_list(request):
    sessions = CashRegisterSession.objects.all().select_related('cashier')
    open_session = sessions.filter(status='open').first()
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

    if request.method == 'POST':
        cutoff_config = CajaConfig.get()
        cutoff = cutoff_config.cutoff_time
        now = timezone.localtime(timezone.now())

        effective_date = now.date()
        if now.time() > cutoff:
            effective_date = now.date() + timedelta(days=1)

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
    }
    return render(request, 'crm/cash_register/session_detail.html', context)
