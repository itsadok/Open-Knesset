# -*- coding: utf-8 -*-
import urllib2, urllib, cookielib, re, gzip, datetime, time, logging, os, sys,traceback, difflib
import codecs
import calendar
import subprocess
from itertools import izip
from urlparse import urljoin
from tempfile import NamedTemporaryFile
from datetime import datetime, timedelta

from cStringIO import StringIO
from pyth.plugins.rtf15.reader import Rtf15Reader
from optparse import make_option

from django.core.management.base import NoArgsCommand
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Max,Count

from knesset.mks.models import Member,Party,Membership,WeeklyPresence
from knesset.persons.models import Person,PersonAlias
from knesset.laws.models import (Vote, VoteAction, Bill, Law, PrivateProposal,
     KnessetProposal, GovProposal, GovLegislationCommitteeDecision)
from knesset.links.models import Link
from knesset.committees.models import Committee,CommitteeMeeting
from knesset.utils import cannonize

import mk_info_html_parser as mk_parser
import parse_presence, parse_laws, mk_roles_parser, parse_remote

from BeautifulSoup import BeautifulSoup

ENCODING = 'utf8'

DATA_ROOT = getattr(settings, 'DATA_ROOT',
                    os.path.join(settings.PROJECT_ROOT, os.path.pardir, os.path.pardir, 'data'))
ANTIWORD = os.path.join(settings.PROJECT_ROOT, os.path.pardir, os.path.pardir, 'parts', 'antiword', 'bin', 'antiword')
if not os.path.exists(ANTIWORD):
    ANTIWORD = 'antiword'

logger = logging.getLogger("open-knesset.get_plenum_data")

class Command(NoArgsCommand):
    option_list = NoArgsCommand.option_list + (
        make_option("--parse",
                    action="store", type="string", dest="filename"),
    )
    help = "Downloads plenum data from sources, parses it and loads it to the Django DB."

    def handle_noargs(self, **options):
        if options.get("filename"):
            self.parse_transcript(options["filename"])
        else:
            self.get_transcripts()

    def get_transcripts_from_queue(self):
        latest_transcripts_url = "http://www.knesset.gov.il/plenum/heb/plenum_queue.aspx"
        page = BeautifulSoup(urllib2.urlopen(latest_transcripts_url))
        for anchor in page.findAll("a", { "href" : re.compile(r"\.doc$")}):
            doc_url = urljoin(latest_transcripts_url, anchor["href"])
            self.get_transcript(doc_url)

    def get_transcripts(self):
        search_page_url = "http://www.knesset.gov.il/plenum/heb/plenum_search.aspx"
        month = YearMonth()

        page = BeautifulSoup(urllib2.urlopen(search_page_url))

        while True:
            params = {}
            for input in page.find("form", {"name": "Form1"}).findAll("input", {"type": "hidden"}):
                params[ input["name"] ] = input["value"]

            for day in range(month.num_days()):
                params["__EVENTTARGET"] = "cldSearchDate"
                params["__EVENTARGUMENT"] = "%s" % (month.days_since_2000() + day)
                params["ddlYearSel"] = "2011"

                print "Checking meetings on %s/%s/%s" % (day+1, month.month, month.year)
                page = BeautifulSoup(urllib2.urlopen(search_page_url, urllib.urlencode(params)))
                time.sleep(1)
                for anchor in page.findAll("a", { "href" : re.compile(r"\.doc$")}):
                    doc_url = urljoin(search_page_url, anchor["href"])
                    self.get_transcript(doc_url)

            month = month.previous_month()

            params["__EVENTTARGET"] = "cldSearchDate"
            params["__EVENTARGUMENT"] = "V%s" % month.days_since_2000()
            params["ddlYearSel"] = "2011"

            print "Going to the page for month %s/%s" % (month.month, month.year)
            page = BeautifulSoup(urllib2.urlopen(search_page_url, urllib.urlencode(params)))
            time.sleep(1)

    def get_transcript(self, doc_url):
        filename = re.findall(r'\w+\.doc$', doc_url)[0]
        print "Saving " + filename
        doc_path = os.path.join(DATA_ROOT, "plenum/doc")
        if not os.path.exists(doc_path):
            os.makedirs(doc_path)
        doc_file = open(os.path.join(doc_path, filename), "w")
        doc_file.write(urllib2.urlopen(doc_url).read())
        doc_file.close()

        try:
            text = subprocess.Popen([ANTIWORD, filename], stdout=subprocess.PIPE).communicate()[0]
            text_path = os.path.join(DATA_ROOT, "plenum/text")
            if not os.path.exists(text_path):
                os.makedirs(text_path)
            text_file = open(os.path.join(text_path, filename.replace(".doc", ".txt")), "w")
            text_file.write(text)
            text_file.close()
        except OSError:
            logger.error("Failed to run antiword on %s" % filename)

    def parse_transcript(self, filename):
        matcher = Matcher()
        transcript = []

        textlines = []
        speaker = None
        state = "cover"
        for line in codecs.open(filename, "r", "utf-8"):
            if state == "cover":
                if line.strip() == u"תוכן עניינים":
                    cover = "".join(textlines)
                    transcript.append( ("cover", cover) )
                    textlines = []
                    state = "toc"
                elif re.search(ur"^<(?!הצע|החלט)", line):
                    textlines = []
                    state = "speaker"
                elif re.search(r"^ *<", line):
                    textlines = []
                    state = "header"

            elif state == "toc":
                if re.search(ur"^<(?!הצע|החלט)", line):
                    textlines = []
                    state = "speaker"
                elif re.search(r"^ *<", line):
                    textlines = []
                    state = "header"

            elif state == "header":
                if re.search(ur"^<(?!הצע|החלט)", line):
                    header = "".join(textlines)
                    transcript.append( (header, "") )
                    textlines = []
                    state = "speaker"

            elif state == "speaker":
                speaker_line = "".join(textlines).replace("\n", "")
                if matcher.search(r'^<(.*?):?>$', speaker_line):
                    speaker = matcher.group(1)
                    textlines = []
                    state = "body"

            elif state == "body":
                if re.search(ur"^<(?!הצע|החלט)", line):
                    body = "".join(textlines)
                    transcript.append( (speaker, body) )
                    speaker = None
                    textlines = []
                    state = "speaker"
                elif re.search(r"^ *<", line):
                    body = "".join(textlines)
                    transcript.append( (speaker, body) )
                    speaker = None
                    textlines = []
                    state = "header"

            textlines += line

        for header, body in transcript:
            print "********************************************************************************************"
            print (header or '').encode("utf-8")
            print "------------------------------------"
            print (body or '').encode("utf-8")





class YearMonth(object):
    def __init__(self, year=None, month=None):
        self.year = year
        self.month = month
        if year is None:
            now = datetime.now()
            self.year = now.year
            self.month = now.month

    def num_days(self):
        return calendar.monthrange(self.year, self.month)[1]

    #noinspection PySimplifyBooleanCheck
    def previous_month(self):
        year = self.year
        month = self.month
        month -= 1
        if month == 0:
            year -= 1
            month = 12
        return YearMonth(year, month)

    def days_since_2000(self):
        return (datetime(self.year, self.month, 1) - datetime(2000, 1, 1)).days

class Matcher(object):
    def __init__(self):
        self.m = None

    def search(self, pattern, string, flags=0):
        self.m = re.search(pattern, string, flags)
        return self.m

    def group(self, *args):
        return self.m.group(*args)

    def groups(self):
        return self.m.groups()
