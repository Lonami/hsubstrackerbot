from json import load
from collections import namedtuple
from database import *
from bs4 import BeautifulSoup
from re import sub, findall
import requests
import logging

logger = logging.getLogger(__name__)


class ScheduleGenerator:
    """
    Class that generates the schedule by scraping HS's schedule page.
    """

    def __init__(self):
        self.config = load(open('config.json', 'r'))
        self.days = self.config['en_gb']['day_array']
        self.show = namedtuple('Show', ['day', 'title', 'time', 'link'])
        self.schedulelink = 'https://horriblesubs.info/release-schedule/'
        self.baselink = 'https://horriblesubs.info'
        self.req = requests.get(self.schedulelink).text
        self.soup = BeautifulSoup(self.req, 'lxml')
        self.id = 0

    def iter_schedule(self, days=None):
        for titleElem, timeElem in zip(self.soup.find_all(attrs={'title': 'See all releases for this show'}),
                                       self.soup.find_all(attrs={'schedule-time'})):

            day = sub(r" \((.*?)\)", "", titleElem.find_previous(attrs={'weekday'}).contents[0])
            titlecheck = titleElem.find(attrs={'data-cfemail': True})
            title = titleElem.contents[0]
            time = timeElem.contents[0]
            link = self.baselink + titleElem.get('href')

            if titlecheck is not None:
                title = sub(r"\[(.*?)\]", self.decode(titlecheck.get("data-cfemail")), titleElem.getText())

            if days is None:
                yield self.show(day, title, time, link)

            elif days in day:
                yield self.show(day, title, time, link)

            else:
                pass

    @staticmethod
    def check_show_internal_id(link):
        for element in BeautifulSoup(requests.get(link).text, 'lxml').find_all(attrs={'type': 'text/javascript'}):
            if 'hs_showid' in element.getText():
                return findall(r"\d+", element.getText())[0]

    @staticmethod
    def check_show_up(link):
        show_id = ScheduleGenerator.check_show_internal_id(link)
        url = f'https://horriblesubs.info//api.php?method=getshows&type=show&showid={show_id}'
        soup = BeautifulSoup(requests.get(url).text, 'lxml')
        showinfo = soup.find(attrs={'rls-info-container'}).contents[0]
        magnetfind_args = 'a', {'title': 'Magnet Link'}
        ret_si = namedtuple('ShowInfo', ['released', 'title', 'episode', 'magnet480', 'magnet720', 'magnet1080'])

        if showinfo.span.text == "Today":
            magnet480 = soup.find(*magnetfind_args)
            magnet720 = magnet480.find_next(*magnetfind_args)
            magnet1080 = magnet720.find_next(*magnetfind_args)

            return ret_si(True, showinfo.span.next_sibling.strip(), showinfo.strong.text,
                          magnet480.get('href'), magnet720.get('href'), magnet1080.get('href'))

        else:
            return ret_si(False, showinfo.span.next_sibling.strip(), showinfo.strong.text,
                          None, None, None)

    def update_schedule(self):
        # TODO : Rewrite update function to use partial differences instead of deleting everything
        self.req = requests.get(self.schedulelink)
        self.id += 1
        showlist = [show.title for show in self.iter_schedule()]
        
        if showlist == list_all_shows():
            logger.info(f"Update successful, id: {self.id}")
            return True
        else:
            logger.warning("Show mismatch found, flushing old data...")
            delete_data()
            show_insert_loop(self)
            return False

    @staticmethod
    def shorten_magnet(magnet_link):
        r = requests.get(f'http://mgnet.me/api/create?m={magnet_link}')
        return r.json().get('shorturl')

    @staticmethod
    def decode(encstr):
        return ''.join([chr(int(encstr[i:i + 2], 16) ^ int(encstr[:2], 16)) for i in range(2, len(encstr), 2)])


def show_insert_loop(schedule: ScheduleGenerator):
        """
        Grabs all the shows from the schedule and inserts them
        into the database
        """
        logger.info('Entering show_insert_loop...')
        for show in schedule.iter_schedule():
            try:
                insert_show(show.title, show.day, show.time, show.link)
                if not get_internal_show_id(show.title):
                    set_internal_show_id(show.title, schedule.check_show_internal_id(show.link))

            except TransactionIntegrityError:
                pass
