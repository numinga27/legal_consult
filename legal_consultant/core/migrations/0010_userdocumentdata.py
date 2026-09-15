"""Preserve the migration already applied on the existing production server."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0009_conclusion_user_data_fields')]
    operations = [migrations.CreateModel(
        name='UserDocumentData',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('data', models.JSONField(default=dict, verbose_name='Данные пользователя')),
            ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')),
            ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Дата обновления')),
            ('conclusion', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='user_data_entries', to='core.conclusion', verbose_name='Вывод')),
            ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_data', to='core.usersession', verbose_name='Сессия')),
        ],
        options={'verbose_name': 'Данные пользователя', 'verbose_name_plural': 'Данные пользователей'},
    )]
