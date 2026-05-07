"""
Test WhatsApp integration with the latest PO
"""
from django.core.management.base import BaseCommand
from scm.models import PurchaseOrder
from scm.po_pdf import generate_po_pdf
from scm.po_whatsapp import send_po_via_whatsapp
import os


class Command(BaseCommand):
    help = 'Test WhatsApp integration with the latest purchase order'

    def add_arguments(self, parser):
        parser.add_argument(
            '--po-id',
            type=int,
            help='Specific PO ID to test with (defaults to latest)',
        )

    def handle(self, *args, **options):
        po_id = options.get('po_id')
        
        if po_id:
            try:
                po = PurchaseOrder.objects.get(id=po_id)
            except PurchaseOrder.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'PO with ID {po_id} not found'))
                return
        else:
            po = PurchaseOrder.objects.order_by('-created_date').first()
            if not po:
                self.stdout.write(self.style.ERROR('No purchase orders found'))
                return
        
        self.stdout.write(f'\n📦 Testing WhatsApp with PO: {po.po_number}')
        self.stdout.write(f'Provider: {po.provider.name}')
        self.stdout.write(f'Phone: {po.provider.phoneNumber}')
        self.stdout.write(f'Status: {po.get_status_display()}')
        
        # Check environment variables
        account_sid = os.getenv('WHATSAPP_ACCOUNT_SID', '').strip()
        auth_token = os.getenv('WHATSAPP_AUTH_TOKEN', '').strip()
        from_number = os.getenv('WHATSAPP_FROM_NUMBER', '').strip()
        
        self.stdout.write('\n🔐 Twilio Configuration:')
        self.stdout.write(f'  Account SID: {"✓ Set" if account_sid else "✗ Not set"}')
        self.stdout.write(f'  Auth Token: {"✓ Set" if auth_token else "✗ Not set"}')
        self.stdout.write(f'  From Number: {from_number if from_number else "✗ Not set"}')
        
        if not all([account_sid, auth_token, from_number]):
            self.stdout.write(self.style.WARNING(
                '\n⚠️  WhatsApp not fully configured. Set these environment variables:\n'
                '   WHATSAPP_ACCOUNT_SID\n'
                '   WHATSAPP_AUTH_TOKEN\n'
                '   WHATSAPP_FROM_NUMBER'
            ))
            return
        
        # Generate PDF
        self.stdout.write('\n📄 Generating PDF...')
        try:
            pdf_content = generate_po_pdf(po)
            self.stdout.write(self.style.SUCCESS(f'✓ PDF generated ({len(pdf_content)} bytes)'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Failed to generate PDF: {str(e)}'))
            return
        
        # Send via WhatsApp
        self.stdout.write('\n📤 Sending via WhatsApp...')
        result = send_po_via_whatsapp(po, pdf_content)
        
        if result['success']:
            self.stdout.write(self.style.SUCCESS(f"✓ {result['message']}"))
            if 'message_sid' in result:
                self.stdout.write(f"  Message SID: {result['message_sid']}")
        else:
            self.stdout.write(self.style.ERROR(f"✗ {result['message']}"))
        
        self.stdout.write('\n')
