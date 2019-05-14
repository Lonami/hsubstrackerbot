from pony.orm import db_session, set_sql_debug, Database, PrimaryKey, Required, Optional, select,\
    TransactionIntegrityError

set_sql_debug(False)
db = Database()


class User(db.Entity):
    tguser_id = PrimaryKey(int)
    tgusername = Required(str)
    tgfirstname = Required(str)


class Show(db.Entity):
    show_id = PrimaryKey(int, auto=True)
    show_title = Required(str, unique=True)
    show_airing_day = Required(str)
    show_airing_time = Required(str)
    show_link = Required(str)
    show_internal_id = Optional(int)


class Subscription(db.Entity):
    ext_user_id = Required(int)
    ext_show_id = Required(int)
    sub_id = PrimaryKey(ext_user_id, ext_show_id)


db.bind(provider='sqlite', filename='data.db', create_db=True)
db.generate_mapping(create_tables=True)


@db_session
def insert_user(userid: int, username: str, firstname: str):
    """
    Inserts a user into the database
    :param userid:
    :param username:
    :param firstname:
    :return:
    """
    User(tguser_id=userid, tgusername=username, tgfirstname=firstname)


@db_session
def insert_show(title: str, airday: str, airtime: str, link: str):
    """
    Inserts a show into the database
    :param title:
    :param airday:
    :param airtime:
    :param link:
    :return:
    """
    Show(show_title=title, show_airing_day=airday, show_airing_time=airtime, show_link=link)


@db_session
def insert_subscription(userid: int, showid: int):
    """
    Inserts a subscription into the database
    :param userid:
    :param showid:
    :return:
    """
    Subscription(ext_user_id=userid, ext_show_id=showid)


@db_session
def remove_subscription(userid: int, showid: int):
    """
    Removes a subscription from the database
    Called only after a check if user is subscribed first
    :param userid:
    :param showid:
    :return:
    """
    select(sub for sub in Subscription if sub.ext_user_id == userid and sub.ext_show_id == showid)[:][0].delete()


@db_session
def get_username_by_userid(userid: int):
    """
    Returns a user's username by his userid
    :param userid:
    :return:
    """
    return select(u.tgusername for u in User if u.tguser_id == userid)[:][0]


@db_session
def get_show_id_by_name(title: str):
    """
    Returns the show's auto-incremented internal id by its title
    :param title:
    :return:
    """
    return select(s.show_id for s in Show if s.show_title == title)[:][0]


@db_session
def get_show_link_by_name(title: str):
    """
    Returns the show's link by its title
    :param title:
    :return:
    """
    return select(s.show_link for s in Show if s.show_title == title)[:][0]


@db_session
def check_subscribed(userid: int, showid: int):
    """
    Checks if a given user is subscribed to a given show
    :param userid:
    :param showid:
    :return:
    """
    return len(select(sub for sub in Subscription if sub.ext_user_id == userid and sub.ext_show_id == showid)[:]) > 0


@db_session
def check_user_exists(userid: int):
    """
    Check whether a user exists in the database
    :param userid:
    :return:
    """
    return len(select(u for u in User if userid == u.tguser_id)[:]) > 0


@db_session
def return_users_subbed(showid: int):
    """
    Returns a list of users that are subscribed to a given show
    :param showid:
    :return:
    """
    return select(sub.ext_user_id for sub in Subscription if sub.ext_show_id == showid)[:]


@db_session
def return_all_users():
    """
    Returns a list of all users who have interacted with the bot
    Could be used for announcements
    :return:
    """
    return select(u.tguser_id for u in User)[:]


@db_session
def delete_data():
    """
    Removes all data from tables Show and Subscription
    Used during updates when there is a show mismatch which would indicate a new season
    :return:
    """
    for item in select(s for s in Show)[:]:
        item.delete()

    for item in select(sub for sub in Subscription)[:]:
        item.delete()


@db_session
def list_all_shows():
    """
    Returns a list of all shows currently in the database
    :return:
    """
    return select(s.show_title for s in Show).order_by(lambda: s.show_id)[:]


@db_session
def get_internal_show_id(title: str):
    """
    Returns the show's HS API internal ID
    :param title:
    :return:
    """
    return Show.get(show_title=title).show_internal_id


@db_session
def set_internal_show_id(title: str, idvalue: int):
    """
    Sets a show's HS API internal ID
    :param title:
    :param idvalue:
    :return:
    """
    Show.get(show_title=title).show_internal_id = idvalue


__all__ = ['insert_show', 'insert_user', 'check_user_exists', 'get_show_id_by_name', 'check_subscribed',
           'insert_subscription', 'remove_subscription', 'return_users_subbed', 'TransactionIntegrityError',
           'delete_data', 'return_all_users', 'list_all_shows', 'get_show_link_by_name', 'get_username_by_userid',
           'get_internal_show_id', 'set_internal_show_id']
