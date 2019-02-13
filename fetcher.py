import urllib2
from bs4 import BeautifulSoup as bs
from urlparse import urljoin
import sys, os, hashlib, re, time, csv

fetch_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 100
fetch_delay = int(sys.argv[3]) if len(sys.argv) > 3 else 10
currently_fetched = 0

bye_string = 'BYE'

def fetch_url(url):
    global currently_fetched
    round_hash = hashlib.sha224(url).hexdigest()
    cache_path = os.path.join('cache', round_hash)
    if not os.path.exists(cache_path):
        print 'Fetching: %s' % (url)
        if currently_fetched > fetch_limit:
            print 'Fetch rate limit reached, delaying for %d seconds.' % (fetch_delay)
            time.sleep(fetch_delay)
            currently_fetched = 0
        r_content = urllib2.urlopen(url).read()
        file(cache_path, 'w').write(r_content)
        currently_fetched += 1
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
                    self.tournaments[tournament_id] = Tournament(self)
                self.tournaments[tournament_id].id = tournament_id
                name = link.text.split()
                if len(name) > 1:
                    self.tournaments[tournament_id].name = name[0]
                session = Session(self.tournaments[tournament_id], link['href'], session_group, session_number, name[-1])
                self.tournaments[tournament_id].sessions.append(session)

    def __repr__(self):
        return self.name

class Tournament(object):
    id = None
    name = None
    sessions = None
    pairs = None
    event = None

    def __init__(self, event):
        self.sessions = []
        self.pairs = {}
        self.event = event

    def __repr__(self):
        return '%s (#%d)' % (self.name, self.id)

class Session(object):
    tournament = None
    link = None
    group_number = None
    round_number = None
    name = None
    content = None
    boards = None
    results = None

    def __init__(self, tournament, link, group_no, round_no, name):
        self.tournament = tournament
        self.link = urljoin(self.tournament.event.link, link.replace('/TotalPairs', '/RoundPairs'))
        self.group_number = group_no
        self.round_number = round_no
        self.name = name
        self.content = bs(fetch_url(self.link), 'lxml')
        self.pair_link_regex = re.compile(
            r'boarddetailspairs\.asp\?qtournid=%d&qgroupno=%d&qroundno=%d&qpairid=(\d+)$' % (
                self.tournament.id, self.group_number, self.round_number
            ),
            flags=re.I)
        self.boards = {}
        self.get_data()

    def get_data(self):
        for row in self.content.select('tr tr'):
            for link in row.select('a[href]'):
                pair_link = self.pair_link_regex.search(link['href'])
                if pair_link:
                    pair_number = int(pair_link.group(1))
                    if pair_number not in self.tournament.pairs:
                        names = [a.text for a in row.select('a[href]') if 'person.asp' in a['href']]
                        nationalities = row.select('td')[-2].text.split(' - ')
                        pair = Pair(pair_number, names, nationalities, self.tournament)
                        self.tournament.pairs[pair_number] = pair
        for row in self.content.select('tr tr'):
            for link in row.select('a[href]'):
                pair_link = self.pair_link_regex.search(link['href'])
                if pair_link:
                    pair_results = bs(fetch_url(urljoin(self.link, link['href'])), 'lxml')
                    for board_link in pair_results.select('a[href]'):
                        if board_link['href'].startswith('BoardAcrosspairs.asp'):
                            board_number = int(board_link.text.strip())
                            if board_number not in self.boards:
                                board = Board(board_number, urljoin(urljoin(self.link, link['href']), board_link['href']), self)
                                self.boards[board_number] = board

    def __repr__(self):
        return '%s %s (#%d/%d/%d)' % (self.tournament.name, self.name, self.tournament.id, self.group_number, self.round_number)

class Pair(object):
    number = None
    names = None
    tournament = None
    nationalities = None

    def __init__(self, number, names, nationalities, tournament):
        self.number = number
        self.names = names
        self.tournament = tournament
        self.nationalities = nationalities

    def __repr__(self):
        return '#%d %s (%s)' % (self.number, ' - '.join(self.names), self.nationalities)

class Board(object):
    link = None
    number = None
    session = None
    results = None
    layout = ''
    suits = {u"\u2665": 'H', u"\u2663": 'C', u"\u2660": 'S', u"\u2666": 'D'}

    def __init__(self, number, link, session):
        self.number = number
        self.link = link
        self.session = session
        self.pair_link_regex = re.compile(r'BoardDetailsPairs\.asp\?qpairid=(\d+)&', flags=re.I)
        self.results = []
        self.get_results()

    def __get_pair(self, cell):
        for link in cell.select('a[href]'):
            pair = self.pair_link_regex.search(link['href'])
            if pair:
                try:
                    return self.session.tournament.pairs[int(pair.group(1))]
                except KeyError:
                    return None

    def __strip_symbols(self, cell):
        text = cell.text.strip()
        for key, repl in self.suits.iteritems():
            text = text.replace(key, repl)
        return text

    def get_results(self):
        results = bs(fetch_url(self.link), 'lxml')
        rows = results.select('table table table tr')
        for row in rows:
            for link in row.select('a[href]'):
                if link['href'].startswith('BoardDetailsPairs.asp'):
                    cells = row.select('td')
                    result = Result()
                    result.board = self
                    result.section = int(cells[0].text.strip())
                    result.table =  int(cells[1].text.strip())
                    result.ns_pair = self.__get_pair(cells[2])
                    result.ew_pair = self.__get_pair(cells[3])
                    result.contract = self.__strip_symbols(cells[4])
                    result.declarer = cells[5].text.strip()
                    result.lead = self.__strip_symbols(cells[6])
                    tricks = cells[7].text.strip()
                    result.tricks = int(tricks) if tricks else 0
                    score = cells[8].text.strip()
                    if len(score):
                        result.score = int(score)
                    else:
                        score = cells[9].text.strip()
                        if len(score):
                            result.score = -int(cells[9].text.strip())
                        else:
                            result.score = 0
                    if not (result.ns_pair and result.ew_pair) and result.score <> 0:
                        raise ValueError('Unknown pair for result: %s' % result)
                    self.results.append(result)
                    break

class Result(object):
    board = None
    section = None
    table = None
    ns_pair = None
    ew_pair = None
    contract = None
    declarer = None
    lead = None
    tricks = None
    score = None

    def __repr__(self):
        return '#%d [%s %s] %s %s %s, %d tricks: %d' % (
            self.board.number,
            str(self.ns_pair.number) if self.ns_pair else bye_string,
            str(self.ew_pair.number) if self.ew_pair else bye_string,
            self.contract, self.declarer, self.lead,
            self.tricks, self.score)

results_url = sys.argv[1]
event = Event(results_url)

print event
for tournament in event.tournaments.values():
    print tournament, tournament.sessions, tournament.pairs
