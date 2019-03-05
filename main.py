import logging
from multiprocessing import Pool
from datetime import datetime, timedelta
from pytz import timezone
from time import strptime
from threading import Timer
from json import load
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Bot, parsemode
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from hsubs import ScheduleGenerator, check_show_up, get_show_ep_magnet
from database import *


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

sc = ScheduleGenerator()

config = load(open('config.json', 'r'))


def show_insert_loop(schedule: ScheduleGenerator):
    """
    Grabs all the shows from the schedule and inserts them
    into the database
    """
    for show in schedule.iter_schedule():
        try:
            insert_show(show.title, show.day, show.time, show.link)
        except TransactionIntegrityError:
            pass


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
    callback_query = update.callback_query.data.split('@')[0]
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


def calc_time(bot_inst):
    """
    Calculates how much time there is until the next show release
    by subtracting the current time from the show release time (release_time - current_time)
    until we get a positive time delta (how much time is remaining until we have to do things)
    """
    logger.info('calc_time entered...')
    if not sc.update_schedule():
        show_insert_loop(sc)
    tz = timezone('US/Pacific')
    day = datetime.now(tz).weekday()
    pst = datetime.now(tz)
    notif_offset = 300

    for show in sc.iter_schedule(sc.days[day]):
        pst_n = strptime(pst.strftime('%H:%M'), '%H:%M')  # current time
        showtime = strptime(show.time, '%H:%M')  # show - upcoming or past
        s_td = timedelta(hours=showtime.tm_hour, minutes=showtime.tm_min)
        pst_td = timedelta(hours=pst_n.tm_hour, minutes=pst_n.tm_min)
        final_td = int((s_td - pst_td).total_seconds())

        if final_td < 0:
            logger.info(f'{show.title} has already aired: {final_td} seconds.')

        else:
            logger.info(f'{show.title}, upcoming in {final_td} seconds.')
            notif_timer = Timer(final_td + notif_offset, send_notif, [bot_inst, show.title])
            logger.debug(notif_timer)
            notif_timer.start()

    # Here we grab the time delta between the last show of today and the first show of tomorrow
    # so we can know how long we have to wait until calculating time again
    # 6 = Sunday, 0 = Monday, fixed so it wraps around
    if day == 6:
        day = -1

    day_tomorrow = day + 1
    ls_td = timedelta(days=day, hours=showtime.tm_hour, minutes=showtime.tm_min)

    for t_show in sc.iter_schedule(sc.days[day_tomorrow]):
        t_showtime = strptime(t_show.time, '%H:%M')
        t_show_td = timedelta(days=day_tomorrow, hours=t_showtime.tm_hour, minutes=t_showtime.tm_min)
        fut_td = int((t_show_td - ls_td).total_seconds())
        logger.info(f'Last show today: {show.title}, first show tomorrow: {t_show.title}')
        logger.info(f'Total amount of time to wait until tomorrow: {final_td + fut_td}')
        calc_timer = Timer((final_td + fut_td) - 60, calc_time, [bot_inst])
        calc_timer.start()
        break


def send_notif(bot, show_title):
    logger.info('Send notif entered...')
    logger.info(f'Sending out notifications for {show_title}...')
    for user in return_users_subbed(get_show_id_by_name(show_title)):
        try:
            with Pool(processes=2) as pool:
                show_up_res = pool.apply_async(check_show_up, (show_title,)).get(timeout=30)
                logger.info(f'{show_title} - result from check_show_up: {show_up_res}')
                if show_up_res:
                    info = pool.apply_async(get_show_ep_magnet, (show_title,)).get(timeout=30)
                    bot.sendMessage(chat_id=user,
                                    text=f'Hello, @{get_username_by_userid(user)}!\n'
                                    f'{show_title} - {info[0]} is out!\n'
                                    f'• 720p: <a href="{sc.shorten_magnet(info[1])}">click</a>\n'
                                    f'• 1080p:  <a href="{sc.shorten_magnet(info[2])}">click</a>',
                                    parse_mode=parsemode.ParseMode.HTML, disable_web_page_preview=True)
                else:
                    bot.sendMessage(chat_id=user, text=f"{show_title} was supposed to already be out but it isn't!\n"
                                                       "It might've finished airing or there might be delays.\n"
                                                       "For more info, please check the site!")
        except Exception as e:
            logger.warning(f'send_notif failed with exception: {e}')
            pass


def main():
    show_insert_loop(sc)
    updater = Updater(config['token'])
    bot = Bot(config['token'])
    calc_time(bot)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CallbackQueryHandler(handle_button_press))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
