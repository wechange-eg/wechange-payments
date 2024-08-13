# Generated by Django 3.2.18 on 2023-09-01 12:10

from django.conf import settings
import django.core.serializers.json
from django.db import migrations, models
import django.db.models.deletion
import wechange_payments.utils.utils


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('wechange_payments', '0015_auto_20220117_1742'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='payment',
            field=models.OneToOneField(editable=False, help_text='The payment for which this main invoice is created.', on_delete=django.db.models.deletion.PROTECT, related_name='invoice', to='wechange_payments.payment', verbose_name='Payment'),
        ),
        migrations.CreateModel(
            name='AdditionalInvoice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state', models.PositiveSmallIntegerField(choices=[(0, 'Not created at provider.'), (1, 'Created, but not finalized'), (2, 'Finalized, but not downloaded'), (3, 'Downloaded and ready')], default=0, editable=False, help_text="An invoice's state can only ever increase.", verbose_name='Invoice State')),
                ('is_ready', models.BooleanField(default=False, help_text='An indicator flag to show that the invoice has been created in the invoice provider and can be downloaded', verbose_name='Is Ready')),
                ('file', models.FileField(blank=True, editable=False, max_length=250, null=True, upload_to=wechange_payments.utils.utils._get_invoice_filename, verbose_name='File')),
                ('provider_id', models.CharField(blank=True, editable=False, max_length=255, null=True, verbose_name='Provider Invoice ID')),
                ('backend', models.CharField(editable=False, max_length=255, verbose_name='Invoice Provider Backend class used')),
                ('extra_data', models.JSONField(blank=True, encoder=django.core.serializers.json.DjangoJSONEncoder, help_text='This may contain the download path or similar IDs to retrieve the file from the provider.', null=True)),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Created')),
                ('last_action_at', models.DateTimeField(auto_now=True, help_text='Used to indicate when the last attempt to retrieve the invoice from the provider was made, so not to spam them in case their API is down.', verbose_name='Last Action At')),
                ('payment', models.ForeignKey(blank=True, editable=False, help_text='The payment of this additional invoice.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='additional_invoices', to='wechange_payments.payment', verbose_name='Payment')),
                ('user', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='additional_invoices', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={
                'verbose_name': 'Additional Invoice',
                'verbose_name_plural': 'Additional Invoices',
                'ordering': ('-created',),
                'abstract': False,
            },
        ),
    ]