# -*- coding: utf-8 -*-
import django.dispatch as dispatch

""" Called after a new user voluntarily signs up on the portal, using the web frontend """
success_email_sender = dispatch.Signal(providing_args=["to_email", "template", "subject_template", "data"])

""" Called after a payment has been successfully processed (its status set to PAID) """
successful_payment_made = dispatch.Signal(providing_args=["payment"],)
