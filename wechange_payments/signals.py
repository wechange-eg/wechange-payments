# -*- coding: utf-8 -*-
import django.dispatch as dispatch

""" Used to dispatch email message information to for an email that is supposed to be 
    sent, if `PAYMENTS_USE_HOOK_INSTEAD_OF_SEND_MAIL` is True.
    If so, implement a listener for this signal in your main app! """
success_email_sender = dispatch.Signal()  # providing_args=["to_user", "template", "subject_template", "data"]

""" Called after a payment has been successfully processed (its status set to PAID) """
successful_payment_made = dispatch.Signal()  # providing_args=["payment"]
