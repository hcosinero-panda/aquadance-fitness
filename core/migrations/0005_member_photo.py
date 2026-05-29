# Migration to add photo field to Member model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_replace_uuid_with_member_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='photo',
            field=models.ImageField(blank=True, help_text='Member profile photo for visual identification', null=True, upload_to='member_photos/'),
        ),
    ]
