# Generated migration for adding unique_code to Member model

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_payment_expiration_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='unique_code',
            field=models.UUIDField(default=uuid.uuid4, editable=False, help_text='Unique code for QR code generation', unique=True),
        ),
    ]
