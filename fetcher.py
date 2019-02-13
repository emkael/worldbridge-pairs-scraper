import urllib2
from bs4 import BeautifulSoup as bs
import sys, os, hashlib, re

def fetch_url(url):
    round_hash = hashlib.sha224(url).hexdigest()
    cache_path = os.path.join('cache', round_hash)
    if not os.path.exists(cache_path):
        r_content = urllib2.urlopen(url).read()
        file(cache_path, 'w').write(r_content)
    else:
        r_content = file(cache_path).read()
    return r_content

class Event(object):
    link = None
    name = None
    tournaments = None
    results = None
    session_link_regex = re.compile(r'/TotalPairs\.asp\?qtournid=(\d+)&qroundno=(\d+)&qgroupno=(\d+)$', flags=re.I)

    def __init__(self, link):
        self.link = link
        self.tournaments = {}
        self.results = bs(fetch_url(self.link), 'lxml')
        self.name = self.results.find('title').text
        self.get_tournaments()

    def get_tournaments(self):
        for link in self.results.select('a[href]'):
            session_link = self.session_link_regex.search(link['href'])
            if session_link:
                tournament_id = int(session_link.group(1))
                session_number = int(session_link.group(2))
                session_group = int(session_link.group(3))
                if tournament_id not in self.tournaments:
                    self.tournaments[tournament_id] = Tournament()
                self.tournaments[tournament_id].id = tournament_id
                name = link.text.split()
                if len(name) > 1:
                    self.tournaments[tournament_id].name = name[0]
                session = Session(link.href, session_group, session_number, name[-1])
                session.tournament = self.tournaments[tournament_id]
                self.tournaments[tournament_id].sessions.append(session)

    def __repr__(self):
        return self.name

class Tournament(object):
    id = None
    name = None
    sessions = None

    def __init__(self):
        self.sessions = []

    def __repr__(self):
        return '%s (#%d)' % (self.name, self.id)

class Session(object):
    tournament = None
    link = None
    group_number = None
    round_number = None
    name = None

    def __init__(self, link, group_no, round_no, name):
        self.link = link.replace('/TotalPairs', '/RoundPairs')
        self.group_number = group_no
        self.round_number = round_no
        self.name = name

    def __repr__(self):
        return '%s (#%d/%d/%d)' % (self.name, self.tournament.id, self.group_number, self.round_number)

results_url = sys.argv[1]
event = Event(results_url)

print event
for tournament in event.tournaments.values():
    print tournament, tournament.sessions
