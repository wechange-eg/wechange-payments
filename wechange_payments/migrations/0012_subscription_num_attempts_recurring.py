# Generated by Django 2.1.10 on 2019-11-13 15:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wechange_payments', '0011_auto_20191111_1855'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='num_attempts_recurring',
            field=models.PositiveSmallIntegerField(default=0, editable=False, help_text='If booking a recurring payment for a subscription fails for non-payment-specific reasons, (e.g.. payment provider is down), we use this to count up attempts to retry.', verbose_name='Attempts of booking recurring payment'),
        ),
    ]