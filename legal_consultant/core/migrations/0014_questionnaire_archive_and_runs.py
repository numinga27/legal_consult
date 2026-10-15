import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('core', '0013_conclusiondocument')]
    operations = [
        migrations.AddField(model_name='questionnaire', name='is_archived', field=models.BooleanField('В архиве', default=False)),
        migrations.CreateModel(name='QuestionnaireRun', fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('started_at', models.DateTimeField(auto_now_add=True)),
            ('completed_at', models.DateTimeField(null=True, blank=True)),
            ('questionnaire', models.ForeignKey(to='core.questionnaire', on_delete=django.db.models.deletion.CASCADE, related_name='runs')),
        ]),
    ]
