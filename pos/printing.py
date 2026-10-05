"""ESC/POS builders for the tablet print bridge.

All formatting lives on the server. The tablet app only writes the resulting
bytes to the Bluetooth (SPP) printer, so any device/browser can trigger a job.
Ported from the old local ``ticket_printer/main.py`` server.
"""

import re
import unicodedata

from django.conf import settings

INIT = b'\x1b\x40'          # ESC @  -> initialize
ALIGN_LEFT = b'\x1b\x61\x00'

LINE_WIDTH = 32             # 58mm paper, Font A

TICKET_LABELS = {
    'sale': 'Venta',
    'quote': 'Cotizacion',
    'devolution': 'Devolucion',
}


def clean_text(text):
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-zA-Z0-9\s\#\$\-\.\,]', '', text)
    return text


def title_case(text):
    text = clean_text(text).lower()
    return ' '.join(w.capitalize() for w in text.split())


def _format_date(raw):
    if hasattr(raw, 'strftime'):
        try:
            return raw.strftime('%d/%m/%Y %H:%M')
        except Exception:
            return str(raw)
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(raw).replace('Z', '+00:00')).strftime('%d/%m/%Y %H:%M')
    except (ValueError, AttributeError):
        return str(raw or '')


def format_ticket(sale_data, store_name, ticket_type='sale'):
    s = sale_data
    store = clean_text(store_name)
    label = TICKET_LABELS.get(ticket_type, TICKET_LABELS['sale'])
    w = LINE_WIDTH
    lines = []
    lines.append('')
    lines.append(store.center(w))
    lines.append('')
    lines.append('-' * w)
    lines.append(f"{label}: #{s['sale_id']}")
    lines.append(f"Fecha: {_format_date(s.get('date'))}")
    lines.append(f"Cliente: {s.get('client', '')}")
    lines.append('-' * w)
    lines.append(f"{'Cantidad':>8} {'Precio':>10} {'Total':>12}")
    lines.append('-' * w)
    for item in s.get('items', []):
        name = title_case(item.get('name', ''))[:w]
        qty = f"{float(item.get('quantity', 0)):.0f}".rjust(8)
        price = f"${float(item.get('price', 0)):.0f}".rjust(10)
        total = f"${float(item.get('item_total', 0)):.0f}".rjust(12)
        lines.append(name)
        lines.append(f"{qty} {price} {total}")
    lines.append('-' * w)
    total_str = f"${float(s.get('total', 0)):.0f}"
    lines.append(f"{'TOTAL:':>19}  {total_str:>11}")
    lines.append('')
    lines.append('Gracias por su compra!'.center(w))
    lines.append('')
    lines.append('Devoluciones maximo tres dias'.center(w))
    lines.append('despues de la compra, presente'.center(w))
    lines.append('ticket y producto en buen estado'.center(w))
    lines.append('')
    return '\n'.join(lines)


def _encode(text):
    return text.encode('cp437', errors='replace')


def build_ticket_bytes(sale_data, ticket_type='sale', store_name=None):
    """Return the full ESC/POS byte stream for a ticket."""
    if store_name is None:
        store_name = getattr(settings, 'STORE_NAME', 'Ferreteria Leon')
    text = format_ticket(sale_data, store_name, ticket_type)
    # This printer has no auto-cutter: finish with paper feed only.
    return INIT + ALIGN_LEFT + _encode(text) + b'\n\n\n'


# ─── Label sheet PDF (A4 letter-style, 14 x 16 = 224 labels) ───────
# Ported from the old local server so labels are generated as a PDF file
# (printed on a normal printer), NOT sent to the thermal ticket printer.

def generate_barcode_pdf(number, sheets=1, blank=False):
    """Return a BytesIO with one barcode repeated across a 14x16 sheet grid."""
    from io import BytesIO
    from reportlab.graphics.barcode import code128
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm

    COLS = 14
    ROWS = 16
    MARGIN = 6 * mm
    MARGIN_B = 4 * mm

    SHEET_W = 279 * mm
    SHEET_H = 215 * mm

    LABEL_W = 19 * mm
    LABEL_H = (SHEET_H - MARGIN - MARGIN_B) / ROWS

    OFFSET_X = 2 * mm
    OFFSET_Y = -2 * mm

    MARGIN_L = (SHEET_W - COLS * LABEL_W) / 2 + OFFSET_X
    MARGIN_T = MARGIN + OFFSET_Y

    BARCODE_MAX_W = LABEL_W * 0.85

    def get_barcode_drawing(data):
        return code128.Code128(str(data), barHeight=10 * mm, barWidth=0.15 * mm,
                               quiet=False, humanReadable=False)

    def draw_barcode(c, bc, x, y):
        w = bc.width
        h = bc.height
        scale = min(BARCODE_MAX_W / w if w > 0 else 1, 1.0)
        if scale < 1.0:
            c.saveState()
            c.translate(x + (LABEL_W - w * scale) / 2,
                        y + (LABEL_H - h * scale) / 2)
            c.scale(scale, scale)
            bc.drawOn(c, 0, 0)
            c.restoreState()
        else:
            bx = x + (LABEL_W - w) / 2
            by = y + (LABEL_H - h) / 2
            bc.drawOn(c, bx, by)

    sheets = max(1, int(sheets or 1))
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(SHEET_W, SHEET_H))
    for sheet in range(sheets):
        bc = get_barcode_drawing(number) if not blank else None
        for row in range(ROWS):
            for col in range(COLS):
                x = MARGIN_L + col * LABEL_W
                y = MARGIN_T + (ROWS - 1 - row) * LABEL_H
                if blank:
                    c.setStrokeColorRGB(0, 0, 0)
                    c.setLineWidth(0.5)
                    c.rect(x, y, LABEL_W, LABEL_H)
                else:
                    draw_barcode(c, bc, x, y)
        if sheet < sheets - 1:
            c.showPage()
    c.save()
    buf.seek(0)
    return buf
