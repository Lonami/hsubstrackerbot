import logging
from datetime import datetime, timedelta
from pytz import timezone
from time import strptime
from json import load
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from hsubs import ScheduleGenerator, show_insert_loop
from database import *


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

sc = ScheduleGenerator()

config = load(open('config.json', 'r'))


def build_button_list(days=False, show=False, rtitle=None, gen_whichday=None, u_id=None):
    """
    Generates the appropriate button list depending on the
    given state
    """
    if days:
        return [[Button.inline(day)] for day in sc.days]

    if not show:
        return None

    buttons = []
    for show in sc.iter_schedule(gen_whichday):
        check = ''
        if rtitle == show.title or check_subscribed(userid=u_id, showid=get_show_id_by_name(show.title)):
            check = '✅ '

        buttons.append([Button.inline(f'{check}{show.title} @ {show.time} PST', show.title)])

    buttons.append([Button.inline('⏪ Back', 'back')])
    return buttons


@events.register(events.CallbackQuery)
async def handle_button_press(event: events.CallbackQuery.Event):
    """
    Handles any button presses via in-place
    message editing
    """
    data = event.data.decode()

    if data in sc.days:
        await event.edit(f'{config["en_gb"]["shows_day"]} {data} :',
                         buttons=build_button_list(show=True, gen_whichday=data, u_id=event.chat_id))

    elif 'back' in data:
        await event.edit(config['en_gb']['pick_day'],
                         buttons=build_button_list(days=True))

    elif check_subscribed(event.chat_id, get_show_id_by_name(data)):
        message = await event.get_message()
        day_context = message.raw_text.split(' ')[5]  # what a hack
        remove_subscription(event.chat_id, get_show_id_by_name(data))
        await event.edit(buttons=build_button_list(show=True, gen_whichday=day_context, u_id=event.chat_id))

    else:
        message = await event.get_message()
        day_context = message.raw_text.split(' ')[5]  # what a heck
        insert_subscription(event.chat_id, get_show_id_by_name(data))
        await event.edit(buttons=build_button_list(show=True, gen_whichday=day_context, rtitle=data, u_id=event.chat_id))


@events.register(events.NewMessage(pattern='/start'))
async def start_command(event):
    if not event.is_private:
        await event.respond(config['en_gb']['pm_only'])
        return

    user = await event.get_sender()
    if check_user_exists(user.id):
        await event.respond(config['en_gb']['greet_seen'],
                            buttons=build_button_list(days=True))
    else:
        insert_user(user.id, user.username, user.first_name)
        await event.respond(config['en_gb']['greet_notseen'],
                            buttons=build_button_list(days=True))


def schedule_notifs_today(bot, last_show_title=None):
    logger.info('schedule_notifs_today entered...')
    if not sc.update_schedule():
        show_insert_loop(sc)

    tz = timezone('US/Pacific')
    today = datetime.now(tz).weekday()
    time_tz = datetime.now(tz)
    notif_offset = 300

    for show in sc.iter_schedule(sc.days[today]):
        time_tz_now = strptime(time_tz.strftime('%H:%M'), '%H:%M')
        showtime = strptime(show.time, '%H:%M')

        tz_now_td = timedelta(hours=time_tz_now.tm_hour, minutes=time_tz_now.tm_min)
        showtime_td = timedelta(hours=showtime.tm_hour, minutes=showtime.tm_min)

        total_time_td = int((showtime_td - tz_now_td).total_seconds())

        if show.title == list(sc.iter_schedule(sc.days[today]))[~0].title:
            schedule_tomorrow(bot, today, show, total_time_td)

        if total_time_td > 0:
            logger.info(f"{show.title} in {total_time_td} seconds.")
            bot.loop.call_later(total_time_td + notif_offset, send_notif, bot, show)

        elif total_time_td in range(-notif_offset, 1) and show.title != last_show_title:
            logger.info(f"{show.title} was in the offset range, ({total_time_td}) scheduling immediately...")
            send_notif(bot, show)

        else:
            logger.info(f"{show.title} has already aired: {total_time_td} seconds.")
            continue

        break


def schedule_tomorrow(bot, day, last_show, total_time_prev):
    logger.info("schedule_tomorrow entered...")
    tomorrow = (day + 1) % 7
    last_show_time = strptime(last_show.time, '%H:%M')
    last_show_td = timedelta(days=day, hours=last_show_time.tm_hour, minutes=last_show_time.tm_min)

    for first_show in sc.iter_schedule(sc.days[tomorrow]):
        first_show_time = strptime(first_show.time, '%H:%M')
        first_show_td = timedelta(days=day + 1, hours=first_show_time.tm_hour, minutes=first_show_time.tm_min)
        schedule_notifs_in = int((first_show_td - last_show_td).total_seconds())
        bot.loop.call_later(total_time_prev + schedule_notifs_in, schedule_notifs_today, bot)
        logger.info(f"Last show today: {last_show.title}, first show tomorrow: {first_show.title}. Time"
                    f" before rescheduling for tomorrow: {total_time_prev + schedule_notifs_in}")
        break


def send_notif(bot, show):
    bot.loop.create_task(do_send_notif(bot, show))


async def do_send_notif(bot, show):
    logger.info("send_notif entered...")
    logger.info(f"Sending out notifications for {show.title}")
    show_check = sc.check_show_up(show.link)

    if show_check.released:
        subbed_userlist = return_users_subbed(get_show_id_by_name(show.title))
        if subbed_userlist:
            for user in subbed_userlist:
                try:
                    await bot.send_message(
                        user,
                        f"Hello @{get_username_by_userid(user)}!\n"
                        f"{show_check.title} episode {show_check.episode} has released!\n"
                        f"Links:\n"
                        f"• 480p: {sc.shorten_magnet(show_check.magnet480)}\n"
                        f"• 720p: {sc.shorten_magnet(show_check.magnet720)}\n"
                        f"• 1080p: {sc.shorten_magnet(show_check.magnet1080)}\n",
                        link_preview=False
                    )
                    schedule_notifs_today(bot, show.title)

                except Exception as e:
                    logger.warning(f"An exception occured during send_notif: {str(e)}")
                    schedule_notifs_today(bot, show.title)
        else:
            logger.info(f"No subscriptions found for {show.title}, continuing...")
            schedule_notifs_today(bot, show.title)
    else:
        logger.warning(f"{show_check.title} was supposed to be out but isn't!")
        subbed_userlist = return_users_subbed(get_show_id_by_name(show.title))
        if subbed_userlist:
            for user in subbed_userlist:
                await bot.send_message(
                    user,
                    f"{show.title} was supposed to be out but isn't!"
                    f"Please check the site for further information!"
                )

        schedule_notifs_today(bot, show.title)


def main():
    show_insert_loop(sc)
    bot = TelegramClient('bot', 6, 'eb06d4abfb49dc3eeb1aeb98ae0f581e').start(bot_token=config['token'])
    schedule_notifs_today(bot)

    bot.add_event_handler(start_command)
    bot.add_event_handler(handle_button_press)

    bot.run_until_disconnected()


if __name__ == '__main__':
    main()
