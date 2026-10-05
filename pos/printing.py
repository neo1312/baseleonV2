"""ESC/POS builders for the tablet print bridge.

All formatting lives on the server. The tablet app only writes the resulting
bytes to the Bluetooth (SPP) printer, so any device/browser can trigger a job.
Ported from the old local ``ticket_printer/main.py`` server.
"""

import io
import re
import unicodedata

from django.conf import settings

ESC = b'\x1b'
GS = b'\x1d'
INIT = b'\x1b\x40'          # ESC @  -> initialize
ALIGN_LEFT = b'\x1b\x61\x00'
ALIGN_CENTER = b'\x1b\x61\x01'
TEXT_DOUBLE_HEIGHT = b'\x1b\x21\x10'
TEXT_NORMAL = b'\x1b\x21\x00'

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


# ─── Labels (barcode) ──────────────────────────────────────────────

def _raster_command(img):
    """Wrap a 1-bit PIL image into an ESC/POS GS v 0 raster command."""
    width = img.width
    height = img.height
    width_bytes = (width + 7) // 8
    out = bytearray()
    out += GS + b'v0' + bytes([
        0,
        width_bytes & 0xFF, (width_bytes >> 8) & 0xFF,
        height & 0xFF, (height >> 8) & 0xFF,
    ])
    pixels = img.load()
    black = 0
    for y in range(height):
        row = bytearray(width_bytes)
        for x in range(width):
            if pixels[x, y] == black:
                row[x >> 3] |= (0x80 >> (x & 7))
        out += row
    return bytes(out)


def _barcode_raster(value, max_width=384):
    from barcode import Code128
    from barcode.writer import ImageWriter
    from PIL import Image

    buf = io.BytesIO()
    Code128(str(value), writer=ImageWriter()).write(buf, options={
        'module_width': 0.35,
        'module_height': 10.0,
        'font_size': 0,
        'text_distance': 0,
        'quiet_zone': 1.0,
        'write_text': False,
    })
    buf.seek(0)
    src = Image.open(buf).convert('L')
    src = src.point(lambda p: 255 if p > 128 else 0, '1')
    if src.width > max_width:
        ratio = max_width / src.width
        src = src.resize((max_width, max(1, int(src.height * ratio))))
    canvas = Image.new('1', (max_width, src.height), 1)  # white background
    canvas.paste(src, ((max_width - src.width) // 2, 0))
    return _raster_command(canvas)


def _barcode_native(value):
    data = b'{B' + str(value).encode('ascii', 'ignore')
    n = len(data)
    return GS + b'h' + bytes([80]) + GS + b'w' + bytes([3]) + GS + b'H' + bytes([2]) + GS + b'k' + bytes([73, n]) + data


def build_label_bytes(value, copies=1, blank=False, store_name=None):
    """Return ESC/POS bytes for one or more barcode labels (58mm)."""
    if store_name is None:
        store_name = getattr(settings, 'STORE_NAME', 'Ferreteria Leon')
    mode = getattr(settings, 'LABEL_BARCODE_MODE', 'raster')
    out = bytearray()
    out += INIT + ALIGN_CENTER

    for _ in range(max(1, int(copies or 1))):
        if not blank:
            store = clean_text(store_name)
            if store:
                out += TEXT_NORMAL + _encode(store) + b'\n'
            if mode == 'native':
                out += _barcode_native(value)
                out += b'\n'
            else:
                out += _barcode_raster(value)
                out += b'\n'
            out += TEXT_DOUBLE_HEIGHT + _encode(str(value)) + b'\n' + TEXT_NORMAL
        out += b'\n\n\n'
    return bytes(out)
