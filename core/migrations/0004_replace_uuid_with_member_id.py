# Migration to replace unique_code with member_id

from django.db import migrations, models


def populate_member_ids(apps, schema_editor):
    """Populate member_id field for existing members"""
    Member = apps.get_model('core', 'Member')
    members = Member.objects.all().order_by('id')
    
    for idx, member in enumerate(members, start=1):
        member.member_id = f"MEM-{idx:06d}"
        member.save()


def reverse_populate(apps, schema_editor):
    """Reverse the population"""
    Member = apps.get_model('core', 'Member')
    Member.objects.all().update(member_id='')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_member_unique_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='member_id',
            field=models.CharField(default='', editable=False, help_text='Unique member ID (e.g., MEM-001539)', max_length=20, unique=False),
            preserve_default=False,
        ),
        migrations.RunPython(populate_member_ids, reverse_populate),
        migrations.AlterField(
            model_name='member',
            name='member_id',
            field=models.CharField(editable=False, help_text='Unique member ID (e.g., MEM-001539)', max_length=20, unique=True),
        ),
        migrations.RemoveField(
            model_name='member',
            name='unique_code',
        ),
    ]
