import logging
from datetime import datetime, timedelta
from pytz import timezone
from time import strptime
from threading import Timer
from json import load
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Bot, parsemode
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
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
        return InlineKeyboardMarkup(([[InlineKeyboardButton(day, callback_data=day)] for day in sc.days]))

    if not show:
        return None

    buttons = []
    for show in sc.iter_schedule(gen_whichday):
        check = ''
        if rtitle == show.title or check_subscribed(userid=u_id, showid=get_show_id_by_name(show.title)):
            check = '✅ '

        buttons.append([InlineKeyboardButton(f'{check}{show.title} @ {show.time} PST', callback_data=show.title)])

    buttons.append([InlineKeyboardButton('⏪ Back', callback_data='back')])
    return InlineKeyboardMarkup(buttons)


def handle_button_press(bot, update):
    """
    Handles any button presses via in-place
    message editing
    """
    callback_query = update.callback_query.data
    cbq_id = update.callback_query.id
    msg_id = update.callback_query.message.message_id
    cht_id = update.callback_query.message.chat.id

    if callback_query in sc.days:
        bot.editMessageText(text=f'{config["en_gb"]["shows_day"]} {callback_query} :',
                            chat_id=cht_id, message_id=msg_id)
        bot.editMessageReplyMarkup(chat_id=cht_id, message_id=msg_id,
                                   reply_markup=build_button_list(show=True, gen_whichday=callback_query, u_id=cht_id))
        bot.answerCallbackQuery(callback_query_id=cbq_id)

    elif 'back' in callback_query:
        bot.editMessageText(text=config['en_gb']['pick_day'],
                            chat_id=cht_id, message_id=msg_id)
        bot.editMessageReplyMarkup(chat_id=cht_id, message_id=msg_id, reply_markup=build_button_list(days=True))
        bot.answerCallbackQuery(callback_query_id=cbq_id)

    else:
        if check_subscribed(cht_id, get_show_id_by_name(callback_query)):
            day_context = update.callback_query.message.text.split(' ')[5]  # what a hack
            remove_subscription(cht_id, get_show_id_by_name(callback_query))
            bot.editMessageReplyMarkup(chat_id=cht_id, message_id=msg_id,
                                       reply_markup=build_button_list(show=True, gen_whichday=day_context,
                                                                      u_id=cht_id))
            bot.answerCallbackQuery(callback_query_id=cbq_id)

        else:
            day_context = update.callback_query.message.text.split(' ')[5]
            insert_subscription(cht_id, get_show_id_by_name(callback_query))
            bot.editMessageReplyMarkup(chat_id=cht_id, message_id=msg_id,
                                       reply_markup=build_button_list(show=True, gen_whichday=day_context,
                                                                      rtitle=callback_query, u_id=cht_id))
            bot.answerCallbackQuery(callback_query_id=cbq_id)


def start_command(bot, update):
    if update.message.chat.type == 'private':
        userid = update.message.chat_id
        username = update.message.from_user.username
        firstname = update.message.from_user.first_name

        if check_user_exists(userid):
            bot.sendMessage(chat_id=userid, text=config['en_gb']['greet_seen'],
                            reply_markup=build_button_list(days=True))

        else:
            bot.sendMessage(chat_id=userid, text=config['en_gb']['greet_notseen'],
                            reply_markup=build_button_list(days=True))
            insert_user(userid, username, firstname)

    else:
        bot.sendMessage(chat_id=update.message.chat_id, text=config['en_gb']['pm_only'])


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
            Timer(total_time_td + notif_offset, send_notif, [bot, show]).start()

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
        first_show_td = timedelta(days=tomorrow, hours=first_show_time.tm_hour, minutes=first_show_time.tm_min)
        schedule_notifs_in = int((first_show_td - last_show_td).total_seconds())
        Timer(total_time_prev + schedule_notifs_in, schedule_notifs_today, [bot]).start()
        logger.info(f"Last show today: {last_show.title}, first show tomorrow: {first_show.title}. Time"
                    f" before rescheduling for tomorrow: {total_time_prev + schedule_notifs_in}")
        break


def send_notif(bot, show):
    logger.info("send_notif entered...")
    logger.info(f"Sending out notifications for {show.title}")
    show_check = sc.check_show_up(show.link)

    if show_check.released:
        for user in return_users_subbed(get_show_id_by_name(show.title)):
            try:
                bot.sendMessage(chat_id=user, text=f"Hello @{get_username_by_userid(user)}!\n"
                                f"{show_check.title} episode {show_check.episode} has released!\n"
                                f"Links:\n"
                                f"• 480p: {sc.shorten_magnet(show_check.magnet480)}\n"
                                f"• 720p: {sc.shorten_magnet(show_check.magnet720)}\n"
                                f"• 1080p: {sc.shorten_magnet(show_check.magnet1080)}\n",
                                disable_web_page_preview=True)
                schedule_notifs_today(bot, show.title)

            except Exception as e:
                logger.warning(f"An exception occured during send_notif: {str(e)}")
                schedule_notifs_today(bot, show.title)
    else:
        logger.warning(f"{show_check.title} was supposed to be out but isn't!")
        schedule_notifs_today(bot, show.title)


def main():
    show_insert_loop(sc)
    updater = Updater(config['token'])
    bot = Bot(config['token'])
    schedule_notifs_today(bot)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CallbackQueryHandler(handle_button_press))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
