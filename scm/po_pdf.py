"""
Generate PDF for Purchase Orders
"""
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO
from datetime import datetime


def generate_po_pdf(po):
    """
    Generate a PDF for a Purchase Order.
    Returns bytes of the PDF.
    
    PDF includes:
    - PO Header (number, date, provider)
    - Items table (SKU, Product, Quantity to Order)
    - Excludes pricing information
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1f4788'),
        spaceAfter=12,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#333333'),
        spaceAfter=6,
        spaceBefore=6
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=4
    )
    
    # Build document content
    content = []
    
    # Title
    content.append(Paragraph(f"PURCHASE ORDER", title_style))
    content.append(Spacer(1, 0.2*inch))
    
    # Header information
    header_data = [
        [Paragraph(f"<b>PO Number:</b> {po.po_number}", normal_style), 
         Paragraph(f"<b>Status:</b> {po.get_status_display()}", normal_style)],
        [Paragraph(f"<b>Provider:</b> {po.provider.name}", normal_style), 
         Paragraph(f"<b>Created:</b> {po.created_date.strftime('%Y-%m-%d')}", normal_style)],
        [Paragraph(f"<b>Phone:</b> {po.provider.phoneNumber}", normal_style), 
         Paragraph(f"<b>Items:</b> {po.items.count()}", normal_style)],
    ]
    
    header_table = Table(header_data, colWidths=[3.5*inch, 3.5*inch])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f0f0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    content.append(header_table)
    content.append(Spacer(1, 0.2*inch))
    
    # Items table
    content.append(Paragraph("ORDER ITEMS", heading_style))
    
    items_data = [
        ['SKU', 'Product Description', 'Qty to Order']
    ]
    
    for po_item in po.items.all():
        pv1 = po_item.product.get_pv1(po.provider) if po_item.product else ''
        items_data.append([
            str(pv1) if pv1 else '',
            str(po_item.product.full_name if hasattr(po_item.product, 'full_name') else po_item.product.name),
            str(po_item.ordered_quantity)
        ])
    
    items_table = Table(items_data, colWidths=[1.2*inch, 4.5*inch, 1.3*inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9f9f9')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (2, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
    ]))
    content.append(items_table)
    content.append(Spacer(1, 0.2*inch))
    
    # Footer
    footer_text = Paragraph(
        f"<i>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} - This is an automated order confirmation</i>",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, textColor=colors.grey, alignment=TA_CENTER)
    )
    content.append(footer_text)
    
    # Build PDF
    doc.build(content)
    buffer.seek(0)
    return buffer.getvalue()
