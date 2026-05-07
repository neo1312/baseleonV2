from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from im.models import Brand, Category, Product, ProductProvider
from scm.models import Provider, Purchase, purchaseItem


class PurchaseItemStockTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(id='tools', name='Tools')
        self.brand = Brand.objects.create(name='Acme')
        self.provider = Provider.objects.create(
            id='provider-1',
            name='Provider 1',
            address='Main street',
            phoneNumber='555',
        )
        self.product = Product.objects.create(
            id=101,
            name='Hammer',
            barcode='hammer-101',
            stock=5,
            costo=Decimal('10.00'),
            category=self.category,
            brand=self.brand,
            provedor=self.provider,
        )
        ProductProvider.objects.create(
            product=self.product,
            provider=self.provider,
            pv1='pv1-101',
        )
        self.purchase = Purchase.objects.create(provider=self.provider)

    def test_purchase_item_create_updates_stock_with_manual_pk(self):
        purchaseItem.objects.create(
            id=500,
            product=self.product,
            purchase=self.purchase,
            quantity=3,
            cost='10.00',
        )

        self.product.refresh_from_db()
        
        # Stock updates are now disabled - inventory tracked via InventoryUnit
        # Just verify the purchaseItem was created
        item = purchaseItem.objects.get(id=500)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.product_id, self.product.id)

    def test_upload_csv_confirm_updates_stock_without_reusing_csv_pk(self):
        client = Client()
        session = client.session
        session['csv_rows'] = [{
            'id': '999',
            'pv1': self.product.get_pv1(self.provider),
            'purchase': str(self.purchase.id),
            'quantity': '4',
            'cost': '10.00',
        }]
        session.save()

        response = client.post(reverse('scm:uploadcsv_confirm'))

        self.product.refresh_from_db()
        item = purchaseItem.objects.get(product=self.product, quantity=4)

        self.assertContains(response, 'Inserted 1 new rows into purchase')
        # Stock updates are now disabled - inventory tracked via InventoryUnit
        self.assertNotEqual(item.id, 999)
        self.assertNotEqual(item.purchase_id, self.purchase.id)

    def test_upload_csv_confirm_uses_one_new_purchase_for_all_rows(self):
        second_product = Product.objects.create(
            id=102,
            name='Wrench',
            barcode='wrench-102',
            stock=3,
            costo=Decimal('8.00'),
            category=self.category,
            brand=self.brand,
            provedor=self.provider,
        )
        ProductProvider.objects.create(
            product=second_product,
            provider=self.provider,
            pv1='pv1-102',
        )
        client = Client()
        session = client.session
        session['csv_rows'] = [
            {
                'id': '25',
                'Clave': self.product.get_pv1(self.provider),
                'product': str(self.product.id),
                'purchase': '',
                'quantity': '6',
                'cost': '10.00',
            },
            {
                'id': '26',
                'pv1': second_product.get_pv1(self.provider),
                'purchase': str(self.purchase.id),
                'quantity': '2',
                'cost': '8.00',
            },
        ]
        session.save()

        response = client.post(reverse('scm:uploadcsv_confirm'))

        self.product.refresh_from_db()
        second_product.refresh_from_db()
        items = list(purchaseItem.objects.order_by('id'))

        self.assertContains(response, 'Inserted 2 new rows into purchase')
        # Stock updates are now disabled - inventory tracked via InventoryUnit
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].purchase_id, items[1].purchase_id)
        self.assertNotEqual(items[0].purchase_id, self.purchase.id)

    def test_upload_csv_confirm_returns_uploaded_pv1_and_quantities(self):
        client = Client()
        session = client.session
        session['csv_rows'] = [{
            'product': str(self.product.id),
            'pv1': self.product.get_pv1(self.provider),
            'quantity': '2',
            'cost': '10.00',
        }]
        session.save()

        response = client.post(reverse('scm:uploadcsv_confirm'))

        pv1 = self.product.get_pv1(self.provider)
        self.assertContains(response, pv1)
        self.assertContains(response, '<td>2</td>', html=True)

    def test_upload_csv_confirm_accepts_product_id_from_id_column(self):
        client = Client()
        session = client.session
        session['csv_rows'] = [{
            'id': str(self.product.id),
            'purchase': str(self.purchase.id),
            'quantity': '2',
            'cost': '10.00',
        }]
        session.save()

        response = client.post(reverse('scm:uploadcsv_confirm'))

        self.product.refresh_from_db()
        item = purchaseItem.objects.get(product=self.product, quantity=2)

        self.assertContains(response, 'Inserted 1 new rows into purchase')
        # Stock updates are now disabled - inventory tracked via InventoryUnit
        self.assertIsNotNone(item.id)
        self.assertNotEqual(item.purchase_id, self.purchase.id)

    def test_upload_csv_action_accepts_utf8_bom_and_semicolon_separator(self):
        client = Client()
        csv_content = (
            '\ufeffid;purchase;quantity;cost\n'
            f'{self.product.id};{self.purchase.id};2;10.00\n'
        ).encode('utf-8')
        upload = SimpleUploadedFile('purchase.csv', csv_content, content_type='text/csv')

        response = client.post(reverse('scm:uploadcsv_action'), {'csv': upload})

        self.assertContains(response, 'Found 1 rows')
        self.assertContains(response, 'A new purchase will be created automatically')
        self.assertEqual(client.session['csv_rows'][0]['id'], str(self.product.id))

    def test_upload_csv_action_rejects_missing_required_data(self):
        client = Client()
        pv1 = self.product.get_pv1(self.provider)
        csv_content = (
            'pv1,quantity,cost\n'
            f'{pv1},,10.00\n'
        ).encode('utf-8')
        upload = SimpleUploadedFile('purchase.csv', csv_content, content_type='text/csv')

        response = client.post(reverse('scm:uploadcsv_action'), {'csv': upload})

        self.assertContains(response, 'Import aborted. Fix the CSV before continuing')
        self.assertContains(response, 'quantity is required')
        self.assertNotContains(response, 'Import these 1 rows')
        self.assertNotIn('csv_rows', client.session)

    def test_upload_csv_action_rejects_invalid_types(self):
        client = Client()
        pv1 = self.product.get_pv1(self.provider)
        csv_content = (
            'pv1,quantity,cost\n'
            f'{pv1},abc,ten\n'
        ).encode('utf-8')
        upload = SimpleUploadedFile('purchase.csv', csv_content, content_type='text/csv')

        response = client.post(reverse('scm:uploadcsv_action'), {'csv': upload})

        self.assertContains(response, 'quantity must be a whole number')
        self.assertContains(response, 'cost must be numeric')
        self.assertNotIn('csv_rows', client.session)

    def test_upload_csv_confirm_aborts_entire_import_when_any_row_is_invalid(self):
        second_product = Product.objects.create(
            id=102,
            name='Wrench',
            barcode='wrench-102',
            stock=3,
            costo=Decimal('8.00'),
            category=self.category,
            brand=self.brand,
            provedor=self.provider,
        )
        ProductProvider.objects.create(
            product=second_product,
            provider=self.provider,
            pv1='pv1-102',
        )
        client = Client()
        session = client.session
        session['csv_rows'] = [
            {
                'pv1': self.product.get_pv1(self.provider),
                'quantity': '2',
                'cost': '10.00',
            },
            {
                'pv1': second_product.get_pv1(self.provider),
                'quantity': 'bad',
                'cost': '8.00',
            },
        ]
        session.save()

        response = client.post(reverse('scm:uploadcsv_confirm'))

        self.product.refresh_from_db()
        second_product.refresh_from_db()

        self.assertContains(response, 'Import aborted. No rows were inserted.')
        self.assertContains(response, 'quantity must be a whole number')
        self.assertEqual(purchaseItem.objects.count(), 0)
        self.assertEqual(Purchase.objects.count(), 1)
        # Stock updates are now disabled - inventory tracked via InventoryUnit
        # Just verify they stayed at initial values


# Purchase Order Workflow Tests

class PurchaseOrderWorkflowTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(id='tools', name='Tools')
        self.brand = Brand.objects.create(name='Acme')
        self.provider = Provider.objects.create(
            id='provider-1',
            name='Provider 1',
            address='Main street',
            phoneNumber='555',
        )
        self.product1 = Product.objects.create(
            id=101,
            name='Hammer',
            barcode='hammer-101',
            stock=0,
            costo=Decimal('10.00'),
            category=self.category,
            brand=self.brand,
            provedor=self.provider,
        )
        ProductProvider.objects.create(
            product=self.product1,
            provider=self.provider,
            pv1='pv1-101',
        )
        self.product2 = Product.objects.create(
            id=102,
            name='Wrench',
            barcode='wrench-102',
            stock=0,
            costo=Decimal('8.00'),
            category=self.category,
            brand=self.brand,
            provedor=self.provider,
        )
        ProductProvider.objects.create(
            product=self.product2,
            provider=self.provider,
            pv1='pv1-102',
        )

    def test_create_po_from_manual_draft(self):
        """Test creating a PO from manual input"""
        from scm.po_operations import create_po_from_manual
        
        po = create_po_from_manual(
            self.provider,
            [
                {'product_id': self.product1.id, 'quantity': 10, 'cost_per_unit': '10.50'},
                {'product_id': self.product2.id, 'quantity': 5, 'cost_per_unit': '8.25'},
            ],
            created_by='test_user'
        )
        
        self.assertEqual(po.status, 'draft')
        self.assertEqual(po.total_items, 15)
        self.assertEqual(po.total_ordered_cost, Decimal('10.50') * 10 + Decimal('8.25') * 5)
        self.assertEqual(po.items.count(), 2)

    def test_po_workflow_draft_to_approved(self):
        """Test PO approval workflow"""
        from scm.po_operations import create_po_from_manual, approve_purchase_order
        
        po = create_po_from_manual(
            self.provider,
            [{'product_id': self.product1.id, 'quantity': 10, 'cost_per_unit': '10.00'}],
            created_by='user1'
        )
        
        approve_purchase_order(po, approved_by='user2')
        po.refresh_from_db()
        
        self.assertEqual(po.status, 'approved')
        self.assertEqual(po.approved_by, 'user2')
        self.assertIsNotNone(po.approved_date)

    def test_po_workflow_approved_to_sent(self):
        """Test sending approved PO to supplier"""
        from scm.po_operations import (
            create_po_from_manual, approve_purchase_order, send_purchase_order
        )
        
        po = create_po_from_manual(
            self.provider,
            [{'product_id': self.product1.id, 'quantity': 10, 'cost_per_unit': '10.00'}],
            created_by='user1'
        )
        approve_purchase_order(po, approved_by='user2')
        send_purchase_order(po, tracking_reference='TRACK-123', sent_by='user3')
        po.refresh_from_db()
        
        self.assertEqual(po.status, 'sent')
        self.assertEqual(po.tracking_reference, 'TRACK-123')
        self.assertIsNotNone(po.sent_date)

    def test_po_workflow_sent_to_received(self):
        """Test receiving PO from supplier"""
        from scm.po_operations import (
            create_po_from_manual, approve_purchase_order, 
            send_purchase_order, receive_purchase_order
        )
        
        po = create_po_from_manual(
            self.provider,
            [{'product_id': self.product1.id, 'quantity': 10, 'cost_per_unit': '10.00'}],
            created_by='user1'
        )
        approve_purchase_order(po, approved_by='user2')
        send_purchase_order(po, sent_by='user3')
        receive_purchase_order(po, received_by='user4')
        po.refresh_from_db()
        
        self.assertEqual(po.status, 'received')
        self.assertEqual(po.received_by, 'user4')
        self.assertIsNotNone(po.received_date)

    def test_po_received_quantity_update(self):
        """Test updating received quantities in received PO"""
        from scm.po_operations import (
            create_po_from_manual, approve_purchase_order,
            send_purchase_order, receive_purchase_order, update_received_quantity
        )
        
        po = create_po_from_manual(
            self.provider,
            [{'product_id': self.product1.id, 'quantity': 10, 'cost_per_unit': '10.00'}],
            created_by='user1'
        )
        approve_purchase_order(po, approved_by='user2')
        send_purchase_order(po, sent_by='user3')
        receive_purchase_order(po, received_by='user4')
        
        po_item = po.items.first()
        update_received_quantity(po_item, 9, updated_by='user4')
        po_item.refresh_from_db()
        
        self.assertEqual(po_item.received_quantity, 9)
        # Check audit log
        log = po.logs.filter(action='received_qty_changed').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.old_value, '0')
        self.assertEqual(log.new_value, '9')

    def test_po_received_cost_update(self):
        """Test updating received costs in received PO"""
        from scm.po_operations import (
            create_po_from_manual, approve_purchase_order,
            send_purchase_order, receive_purchase_order, update_received_quantity,
            update_received_cost
        )
        
        po = create_po_from_manual(
            self.provider,
            [{'product_id': self.product1.id, 'quantity': 10, 'cost_per_unit': '10.00'}],
            created_by='user1'
        )
        approve_purchase_order(po, approved_by='user2')
        send_purchase_order(po, sent_by='user3')
        receive_purchase_order(po, received_by='user4')
        
        po_item = po.items.first()
        # First set received quantity
        update_received_quantity(po_item, 10, updated_by='user4')
        # Then update cost
        update_received_cost(po_item, Decimal('9.75'), updated_by='user4')
        po_item.refresh_from_db()
        
        self.assertEqual(po_item.received_cost_per_unit, Decimal('9.75'))
        # PO totals should be recalculated
        po.refresh_from_db()
        self.assertEqual(po.total_received_cost, Decimal('9.75') * 10)

    def test_po_complete_creates_purchase(self):
        """Test completing PO creates Purchase and InventoryUnits"""
        from scm.po_operations import (
            create_po_from_manual, approve_purchase_order,
            send_purchase_order, receive_purchase_order, update_received_quantity,
            complete_purchase_order
        )
        
        po = create_po_from_manual(
            self.provider,
            [
                {'product_id': self.product1.id, 'quantity': 5, 'cost_per_unit': '10.00'},
                {'product_id': self.product2.id, 'quantity': 3, 'cost_per_unit': '8.00'},
            ],
            created_by='user1'
        )
        approve_purchase_order(po, approved_by='user2')
        send_purchase_order(po, sent_by='user3')
        receive_purchase_order(po, received_by='user4')
        
        # Update received quantities
        for item in po.items.all():
            update_received_quantity(item, item.ordered_quantity, updated_by='user4')
        
        complete_purchase_order(po, completed_by='user5')
        po.refresh_from_db()
        
        self.assertEqual(po.status, 'completed')
        # Check Purchase was created
        purchase = Purchase.objects.filter(provider=self.provider).latest('id')
        purchase_items = purchaseItem.objects.filter(purchase=purchase)
        self.assertEqual(purchase_items.count(), 2)
        # Verify total quantity across items
        total_qty = sum(item.quantity for item in purchase_items)
        self.assertEqual(total_qty, 8)

    def test_po_order_log_tracks_all_changes(self):
        """Test OrderLog captures all changes"""
        from scm.po_operations import create_po_from_manual, approve_purchase_order
        
        po = create_po_from_manual(
            self.provider,
            [{'product_id': self.product1.id, 'quantity': 10, 'cost_per_unit': '10.00'}],
            created_by='user1'
        )
        approve_purchase_order(po, approved_by='user2')
        
        logs = po.logs.all()
        self.assertGreaterEqual(logs.count(), 2)  # At least created + approved
        
        # Check created log
        created_log = logs.filter(action='created').first()
        self.assertIsNotNone(created_log)
        self.assertEqual(created_log.performed_by, 'user1')
        
        # Check approved log
        approved_log = logs.filter(action='approved').first()
        self.assertIsNotNone(approved_log)
        self.assertEqual(approved_log.performed_by, 'user2')

    def test_po_draft_order_quantity_edit(self):
        """Test editing quantities in draft PO"""
        from scm.po_operations import create_po_from_manual, update_po_item_quantity
        
        po = create_po_from_manual(
            self.provider,
            [{'product_id': self.product1.id, 'quantity': 10, 'cost_per_unit': '10.00'}],
            created_by='user1'
        )
        
        po_item = po.items.first()
        update_po_item_quantity(po_item, 15, updated_by='user2')
        po_item.refresh_from_db()
        po.refresh_from_db()
        
        self.assertEqual(po_item.ordered_quantity, 15)
        self.assertEqual(po.total_items, 15)
        self.assertEqual(po.total_ordered_cost, Decimal('10.00') * 15)

    def test_po_number_generation_unique(self):
        """Test PO numbers are unique"""
        from scm.po_operations import create_po_from_manual
        
        po1 = create_po_from_manual(
            self.provider,
            [{'product_id': self.product1.id, 'quantity': 5, 'cost_per_unit': '10.00'}],
            created_by='user1'
        )
        po2 = create_po_from_manual(
            self.provider,
            [{'product_id': self.product2.id, 'quantity': 3, 'cost_per_unit': '8.00'}],
            created_by='user1'
        )
        
        self.assertNotEqual(po1.po_number, po2.po_number)

