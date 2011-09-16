import logging, difflib, datetime, re, colorsys
from django.utils.translation import ugettext_lazy
from django.utils.translation import ugettext as _
from django.utils import simplejson as json
from django.views.generic.list_detail import object_list
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404,render_to_response
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.core.cache import cache
from django.template import RequestContext
from django.conf import settings
from tagging.models import TaggedItem
from tagging.utils import get_tag
from actstream import action
from knesset.hashnav import ListView, DetailView, method_decorator
from knesset.laws.models import Bill, PrivateProposal
from knesset.mks.models import Member
from knesset.events.models import Event
from knesset.utils import clean_string
from models import PlenumMeeting, TRANSCRIPT_PAGINATE_BY

logger = logging.getLogger("open-knesset.plenum.views")


class MeetingsListView(ListView):

    def get_context(self):
        context = super(MeetingsListView, self).get_context()
        if not self.items:
            raise Http404
        context['title'] = _('All plenum meetings')
        context['none'] = _('No %(object_type)s found') % {'object_type': PlenumMeeting._meta.verbose_name_plural }
        return context

    def get_queryset (self):
        return PlenumMeeting.objects.all()

class MeetingDetailView(DetailView):

    model = PlenumMeeting

    def get_context_data(self, *args, **kwargs):
        context = super(MeetingDetailView, self).get_context_data(*args, **kwargs)
        meeting = context['object']
        transcript = meeting.transcript
        colors = {}
        speakers = transcript.blocks.order_by('speaker__mk').values_list('header','speaker__mk').distinct()
        n = speakers.count()
        for (i,(p,mk)) in enumerate(speakers):
            (r,g,b) = colorsys.hsv_to_rgb(float(i)/n, 0.5 if mk else 0.3, 255)
            colors[p] = 'rgb(%i, %i, %i)' % (r, g, b)
        context['title'] = _('Plenum meeting on %(date)s') % {'date':meeting.date}
        context['description'] = meeting.title
        context['description'] = clean_string(context['description']).replace('"','')
        page = self.request.GET.get('page',None)
        if page:
            context['description'] += _(' page %(page)s') % {'page':page}
        context['colors'] = colors
        parts_lengths = {}
        for block in transcript.blocks.all():
            parts_lengths[block.id] = len(block.body)
        context['parts_lengths'] = json.dumps(parts_lengths)
        context['paginate_by'] = TRANSCRIPT_PAGINATE_BY
        return context


    @method_decorator(login_required)
    def post(self, request, **kwargs):
        cm = get_object_or_404(PlenumMeeting, pk=kwargs['pk'])
        bill = None
        request = self.request
        user_input_type = request.POST.get('user_input_type')
        if user_input_type == 'bill':
            bill_id = request.POST.get('bill_id')
            if bill_id.isdigit():
                bill = get_object_or_404(Bill, pk=bill_id)
            else: # not a number, maybe its p/1234
                m = re.findall('\d+',bill_id)
                if len(m)!=1:
                    raise ValueError("didn't find exactly 1 number in bill_id=%s" % bill_id)
                pp = PrivateProposal.objects.get(proposal_id=m[0])
                bill = pp.bill

            if bill.stage in ['1','2','-2','3']: # this bill is in early stage, so cm must be one of the first meetings
                bill.first_committee_meetings.add(cm)
            else: # this bill is in later stages
                v = bill.first_vote # look for first vote
                if v and v.time.date() < cm.date:          # and check if the cm is after it,
                    bill.second_committee_meetings.add(cm) # if so, this is a second committee meeting
                else: # otherwise, assume its first cms.
                    bill.first_committee_meetings.add(cm)
            bill.update_stage()
            action.send(request.user, verb='added-bill-to-cm',
                description=cm,
                target=bill,
                timestamp=datetime.datetime.now())

        if user_input_type == 'mk':
            mk_names = Member.objects.values_list('name',flat=True)
            mk_name = difflib.get_close_matches(request.POST.get('mk_name'), mk_names)[0]
            mk = Member.objects.get(name=mk_name)
            cm.mks_attended.add(mk)
            cm.save() # just to signal, so the attended Action gets created.
            action.send(request.user, verb='added-mk-to-cm',
                description=cm,
                target=mk,
                timestamp=datetime.datetime.now())

        return HttpResponseRedirect(".")
