#encoding: UTF-8
from django.conf.urls.defaults import *
from django.utils.translation import ugettext
from knesset.hashnav import ListView, DetailView
from models import *
from views import MeetingsListView, MeetingDetailView

meetings_list = MeetingsListView(queryset = PlenumMeeting.objects.all(), paginate_by=20)
meeting_details = MeetingDetailView.as_view()

plenum_urlpatterns = patterns ('',
    url(r'^plenum/$', meetings_list, name='meetings-list'),
    url(r'^plenum/(?P<pk>\d+)/$', meeting_details, name='plenum-meeting'),
)
