# Generated by Django 2.1.5 on 2019-03-27 15:26

from django.conf import settings
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vendor_transaction_id', models.CharField(help_text='An Id for the payment generated by the Payment Service', max_length=50, verbose_name='Vendor Transaction Id')),
                ('internal_transaction_id', models.CharField(help_text='An Id for the payment generated by us', max_length=50, verbose_name='Internal Transaction Id')),
                ('amount', models.FloatField(default='0.0')),
                ('type', models.PositiveSmallIntegerField(choices=[(0, 'SEPA')], default=0, editable=False, verbose_name='Project Type')),
                ('completed_at', models.DateTimeField(auto_now_add=True, verbose_name='Completed At')),
                ('backend', models.CharField(max_length=50, verbose_name='Backend class used')),
                ('extra_data', django.contrib.postgres.fields.jsonb.JSONField()),
                ('user', models.OneToOneField(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='payments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Portal',
                'verbose_name_plural': 'Portals',
            },
        ),
        migrations.CreateModel(
            name='TransactionLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.CharField(blank=True, max_length=150, null=True, verbose_name='API Endpoint URL')),
                ('type', models.PositiveSmallIntegerField(choices=[(0, 'Direct Request'), (1, 'Received Postback')], default=0, editable=False, verbose_name='Project Type')),
                ('data', django.contrib.postgres.fields.jsonb.JSONField()),
            ],
        ),
    ]
