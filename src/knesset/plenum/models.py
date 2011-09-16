# encoding: utf-8
import re
import logging
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.text import truncate_words
from django.contrib.contenttypes import generic

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from tagging.models import Tag
from annotatetext.models import Annotation
from knesset.committees.models import CommitteeMeeting
from knesset.events.models import Event

TRANSCRIPT_PAGINATE_BY = 400

logger = logging.getLogger("open-knesset.plenum.models")

class PlenumMeeting(models.Model):
    date = models.DateField()
    title = models.CharField(max_length=256)
    mks_attended = models.ManyToManyField('mks.Member', related_name='plenum_meetings')
    transcript_text = models.TextField(null=True,blank=True)
    src_url  = models.URLField(verify_exists=False, max_length=1024,null=True,blank=True)

    class Meta:
        ordering = ('-date',)
        verbose_name = _('Plenum Meeting')
        verbose_name_plural = _('Plenum Meetings')

    def __unicode__(self):
        return self.title

    @models.permalink
    def get_absolute_url(self):
        return 'plenum-meeting', [str(self.id)]

    def _get_tags(self):
        tags = Tag.objects.get_for_object(self)
        return tags

    def _set_tags(self, tag_list):
        Tag.objects.update_tags(self, tag_list)

    tags = property(_get_tags, _set_tags)

    def save(self, **kwargs):
        super(PlenumMeeting, self).save(**kwargs)

class Transcript(models.Model):
    meeting = models.OneToOneField(PlenumMeeting)

class TranscriptBlockManager(models.Manager):
    def list(self):
        return self.order_by("ordinal")

class TranscriptBlock(models.Model):
    transcript = models.ForeignKey(Transcript, related_name='blocks')
    timestamp = models.TimeField()
    ordinal = models.IntegerField()
    header = models.TextField(blank=True)
    body = models.TextField(blank=True)
    speaker = models.ForeignKey('persons.Person', blank=True, null=True, related_name='transcript_blocks')
    objects = TranscriptBlockManager()

    annotatable = True

    def get_absolute_url(self):
        if self.ordinal == 1:
            return self.transcript.meeting.get_absolute_url()
        else:
            page_num = 1 + (self.ordinal-1)/TRANSCRIPT_PAGINATE_BY
            if page_num==1: # this is on first page
                return "%s#speech-%d-%d" % (self.transcript.meeting.get_absolute_url(),
                                            self.transcript.meeting.id, self.ordinal)
            else:
                return "%s?page=%d#speech-%d-%d" % (self.transcript.meeting.get_absolute_url(),
                                                    page_num,
                                                    self.transcript.meeting.id, self.ordinal)

    def __unicode__(self):
        return "%s %s: %s" % (self.transcript.meeting.title, self.header,
                              self.header)


from listeners import *
