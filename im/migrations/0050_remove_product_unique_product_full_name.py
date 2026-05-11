# Generated migration to remove unique_product_full_name constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('im', '0049_alter_product_id'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='product',
            name='unique_product_full_name',
        ),
    ]
