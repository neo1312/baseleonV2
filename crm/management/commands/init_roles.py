"""Initialize user roles and permissions for the system"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = 'Initialize user roles (Admin, Manager, Cashier, Auditor, Buyer) with permissions'

    def handle(self, *args, **options):
        # Define roles and their permissions
        roles_permissions = {
            'Admin': [
                # Full access - all permissions
                'add_product', 'change_product', 'delete_product', 'view_product',
                'add_client', 'change_client', 'delete_client', 'view_client',
                'add_provider', 'change_provider', 'delete_provider', 'view_provider',
                'add_sale', 'change_sale', 'delete_sale', 'view_sale',
                'add_quote', 'change_quote', 'delete_quote', 'view_quote',
                'add_devolution', 'change_devolution', 'delete_devolution', 'view_devolution',
                'add_purchase', 'change_purchase', 'delete_purchase', 'view_purchase',
                'add_purchaseorder', 'change_purchaseorder', 'delete_purchaseorder', 'view_purchaseorder',
                'add_inventoryaudit', 'change_inventoryaudit', 'delete_inventoryaudit', 'view_inventoryaudit',
            ],
            'Manager': [
                # View and some edit permissions, no delete
                'view_product', 'view_client', 'view_provider',
                'view_sale', 'view_quote', 'view_devolution',
                'view_purchase', 'view_purchaseorder',
                'view_inventoryaudit',
                'change_inventoryaudit',  # Can modify audit status
            ],
            'Cashier': [
                # Sales only
                'add_sale', 'change_sale', 'view_sale',
                'add_quote', 'change_quote', 'view_quote',
                'add_devolution', 'change_devolution', 'view_devolution',
                'view_product',  # Read-only products
                'view_client',   # Read-only clients
            ],
            'Auditor': [
                # Audit and reports only
                'add_inventoryaudit', 'change_inventoryaudit', 'view_inventoryaudit',
                'view_product',
            ],
            'Buyer': [
                # Purchases and POs only
                'add_purchase', 'change_purchase', 'delete_purchase', 'view_purchase',
                'add_purchaseorder', 'change_purchaseorder', 'delete_purchaseorder', 'view_purchaseorder',
                'view_product',
                'view_provider',
            ],
        }

        # Create groups and assign permissions
        for role_name, perm_list in roles_permissions.items():
            group, created = Group.objects.get_or_create(name=role_name)
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'✓ Created group: {role_name}'))
            else:
                self.stdout.write(f'→ Group exists: {role_name}')
                # Clear existing permissions
                group.permissions.clear()

            # Assign permissions to group
            for perm_codename in perm_list:
                try:
                    permission = Permission.objects.get(codename=perm_codename)
                    group.permissions.add(permission)
                except Permission.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠ Permission not found: {perm_codename}')
                    )

            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Assigned {group.permissions.count()} permissions')
            )

        self.stdout.write(
            self.style.SUCCESS('\n✓ Role initialization complete!')
        )
        self.print_role_summary()

    def print_role_summary(self):
        """Print summary of roles"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('USER ROLES SUMMARY')
        self.stdout.write('='*60)
        
        for group in Group.objects.all().order_by('name'):
            perms = group.permissions.count()
            self.stdout.write(f'\n{group.name}:')
            self.stdout.write(f'  • {perms} permissions assigned')
            self.stdout.write(f'  • Users: {group.user_set.count()}')
