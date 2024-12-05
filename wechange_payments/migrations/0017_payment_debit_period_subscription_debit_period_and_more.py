# Generated by Django 4.2.14 on 2024-08-14 08:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wechange_payments', '0016_auto_20230901_1410'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='debit_period',
            field=models.CharField(choices=[('m', 'monthly'), ('q', 'quarterly'), ('h', 'half-yearly'), ('y', 'yearly')], default='m', max_length=50, verbose_name='Debiting Period'),
        ),
        migrations.AddField(
            model_name='subscription',
            name='debit_period',
            field=models.CharField(choices=[('m', 'monthly'), ('q', 'quarterly'), ('h', 'half-yearly'), ('y', 'yearly')], default='m', editable=False, help_text='For security reasons, the debit period can not be changed through the admin interface!', max_length=50, verbose_name='Debiting Period'),
        ),
        migrations.AlterField(
            model_name='payment',
            name='amount',
            field=models.FloatField(default='0.0', verbose_name='Monthly Amount'),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='amount',
            field=models.FloatField(default='0.0', editable=False, help_text='For security reasons, the amount can not be changed through the admin interface!', verbose_name='Monthly Amount'),
        ),
    ]