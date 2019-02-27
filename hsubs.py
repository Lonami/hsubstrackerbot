from json import load
from collections import namedtuple
from lxml import html
import requests


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
        print(f"Update successful, id: {self.id}")

    def pretty_print(self):
        for day in self.days:
            print(day)
            for item in self.iter_schedule(day):
                if item.day is day:
                    print(f'• {item.title} @ {item.time} PST')
            print('-----------------------------------------')
