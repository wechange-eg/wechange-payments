# Generated by Django 2.1.5 on 2019-05-27 15:47

from django.db import migrations
from django.db.models import F


def convert_payment_type(apps, schema_editor):
    """ One-Time sets all CosinnusIdeas' `last_updated` field value 
        to its `created` field value.  """
    payment_map = {
        '0': 'dd',
        '1': 'cc',
        '2': 'paypal',
    }
    PaymentClass = apps.get_model("wechange_payments", "Payment")
    for payment in PaymentClass.objects.all():
        payment.type = payment_map.get(payment.type)
        payment.save()
    

class Migration(migrations.Migration):

    dependencies = [
        ('wechange_payments', '0007_auto_20191021_1547'),
    ]

    operations = [
        migrations.RunPython(convert_payment_type, migrations.RunPython.noop),
    ]
