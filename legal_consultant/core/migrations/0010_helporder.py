import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('core', '0009_conclusion_user_data_fields')]
    operations = [migrations.CreateModel(name='HelpOrder', fields=[
        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ('owner_id', models.UUIDField(db_index=True)),
        ('fingerprint', models.CharField(max_length=64, unique=True)),
        ('result_code', models.CharField(max_length=100)),
        ('bundle_index', models.PositiveSmallIntegerField()),
        ('summary', models.JSONField(default=dict)),
        ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
        ('full_name', models.CharField(max_length=200)),
        ('email', models.EmailField(max_length=254)),
        ('phone', models.CharField(max_length=40)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('questionnaire', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='core.questionnaire')),
    ], options={'ordering': ['-created_at']})]
