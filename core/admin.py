from django.contrib import admin

from .models import Seed, Purchase, Sale, ReturnTransaction, JournalEntry

admin.site.register(Seed)
admin.site.register(Purchase)
admin.site.register(Sale)
admin.site.register(ReturnTransaction)
admin.site.register(JournalEntry)