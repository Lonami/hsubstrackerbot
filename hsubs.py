from json import load
from collections import namedtuple
from lxml import html
from requests_html import HTMLSession
from database import list_all_shows, delete_data, get_show_link_by_name
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
        self.info = namedtuple('ShowInfo', ['episode', 'magnet720', 'magnet1080'])
        self.schedulelink = 'https://horriblesubs.info/release-schedule/'
        self.baselink = 'https://horriblesubs.info'
        self.req = requests.get(self.schedulelink)
        self.tree = html.fromstring(self.req.text)
        self.id = 0

    def iter_schedule(self, days=None):
        if not days:
            days = self.days
        elif not isinstance(days, (list, tuple)):
            days = [days]

        for day in days:
            # tables start from 1 rather than from 0, 1 day = 1 table
            dayindex = self.days.index(day) + 1
            expr_str = f'//*[@id="post-63"]/div/table[{dayindex}]'
            table = self.tree.xpath(expr_str)[0].getchildren()

            for item in table:
                title = item.getchildren()[0].getchildren()[0].text
                time = item.getchildren()[1].text
                link = f'{self.baselink}{item.getchildren()[0].getchildren()[0].attrib["href"]}'
                yield self.show(day, title, time, link)

    def update_schedule(self):
        self.req = requests.get(self.schedulelink)
        self.tree = html.fromstring(self.req.text)
        self.id += 1
        showlist = []
        [showlist.append(show.title) for show in self.iter_schedule()]
        if showlist == list_all_shows():
            logger.info(f"Update successful, id: {self.id}")
            return True
        else:
            logger.warning("Show mismatch found, flushing old data...")
            delete_data()
            return False

    def check_show_up(self, show_title=None):
        session = HTMLSession()
        r = session.get(self.baselink)
        r.html.render()
        if show_title.replace('–', '-') in r.html.html:
            return True
        else:
            return False

    def get_show_ep_magnet(self, show_title):
        session = HTMLSession()
        r = session.get(get_show_link_by_name(show_title))
        r.html.render()
        episode = r.html.find('a.rls-label')
        magnets = r.html.find('span.dl-type.hs-magnet-link')
        episode = episode[0].text.split(' ')[-2]
        magnet720 = magnets[1].absolute_links.pop()
        magnet1080 = magnets[2].absolute_links.pop()
        return self.info(episode, magnet720, magnet1080)

    @staticmethod
    def shorten_magnet(magnet_link):
        r = requests.get(f'http://mgnet.me/api/create?m={magnet_link}')
        return r.json().get('shorturl')

    def pretty_print(self):
        for day in self.days:
            print(day)
            for item in self.iter_schedule(day):
                if item.day == day:
                    print(f'• {item.title} @ {item.time} PST')
            print('-----------------------------------------')
