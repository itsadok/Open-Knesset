from knesset.plenum.models import PlenumMeeting, Transcript, TranscriptBlock

from django import forms
from django.contrib import admin

class PlenumMeetingAdmin(admin.ModelAdmin):
    ordering = ('-date',)
admin.site.register(PlenumMeeting, PlenumMeetingAdmin)

class TranscriptAdmin(admin.ModelAdmin):
    pass
admin.site.register(Transcript, TranscriptAdmin)

class TranscriptBlockAdmin(admin.ModelAdmin):
    ordering = ('timestamp',)
admin.site.register(TranscriptBlock, TranscriptBlockAdmin)

