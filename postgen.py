import requests
import datetime
import validators
import hashlib
import json
from time import sleep
from csv import DictReader
from operator import itemgetter
from os.path import isfile

def _response_code(url):
    urls = {}
    if isfile('urls.json'):
        f = open('urls.json', 'r')
        urls = json.load(f)
        f.close()
        if url in urls.keys():
            return urls[url]

    code = 429
    i = 0
    while code != 200 and code != 404 and i < 20:
        if 'reddit' in url or (i > 1 and code == 429):
            sleep(1 + i * 0.2)

        r = requests.head(url)
        code = r.status_code
        i += 1

    if code == 200 or code == 404:
        urls[url] = code
        f = open('urls.json', 'w')
        json.dump(urls, f)
        f.close()

    return code

def _get_submission_datetime(substr):
    parts = substr.split()

    day = parts[0].split("/")
    year = int(day[2])
    month = int(day[0])
    day = int(day[1])

    time = parts[1].split(":")
    hour = int(time[0])
    minute = int(time[1])
    sec = int(time[2])

    return datetime.datetime(year, month, day, hour, minute, sec)

def _get_start_end_datetime(date, year, time):
    parts = time.split()

    time = parts[0].split(":")
    hour = int(time[0])
    minute = int(time[1])
    sec = int(time[2])

    day = date.split("/")
    month = int(day[0])
    day = int(day[1])

    meridian = parts[1].strip()
    if meridian == 'PM' and hour < 12:
        hour += 12
    elif meridian == 'AM' and hour == 12:
        hour = 0
        day += 1

    return datetime.datetime(year, month, day, hour, minute, sec)

def _does_user_exist(username):
    ''' (str) -> boolean

        Takes the username of a user as a string and returns a
        boolean representing if this user exists.

        Sometimes it will fail to query reddit properly and just
        return True.

        Currently implemented by naively checking if the user pages
        returns a 200 response. Should use the reddit API properly
        for faster and more intelligent queries.
    '''

    return 200 == _response_code('https://www.reddit.com/user/' + username)

def _h(w):
    return hashlib.md5(w.encode('utf-8')).hexdigest()[:9]

def _get_sheet():
    r = requests.get('https://docs.google.com/spreadsheets/d/1LqM-N1kFa6VUkD3IKhGRZyf9KICIyi3D87Y77seEa4I/export?format=csv&id=1LqM-N1kFa6VUkD3IKhGRZyf9KICIyi3D87Y77seEa4I')
    r.encoding = 'utf-8'

    raw_sheet = r.text

    uid = _h(raw_sheet)
    print('UID: ' + uid)

    updated = True
    if isfile('uid.txt'):
        f = open('uid.txt', 'r')
        old_uid = f.read()
        f.close()

        if uid == old_uid:
            updated = False

    if updated:
        f = open('uid.txt', 'w')
        f.write(uid)
        f.close()

    return updated, raw_sheet

def _get_events(raw_sheet):
    raw_events = list(DictReader(raw_sheet.split("\r\n")))

    events = []
    for revent in raw_events:
        # Do some validation to mitigate spam and throw out old events
        sbmn_datetime = _get_submission_datetime(revent['Timestamp'])
        start_datetime = _get_start_end_datetime(revent['Date'], sbmn_datetime.year, revent['Start Time'])
        if revent['End Time'] != '':
            end_datetime = _get_start_end_datetime(revent['Date'], sbmn_datetime.year, revent['End Time'])

            if end_datetime < start_datetime:
                end_datetime += datetime.timedelta(days=1)

            # Check if the time is sensible / still relevent
            if end_datetime < datetime.datetime.now():
                continue
            elif end_datetime < start_datetime:
                continue
        else:
            if start_datetime < datetime.datetime.now():
                continue

        # Check if valid url
        url = revent['Link'].strip()
        if url != '' and not validators.url(url):
            continue

        # Check if user is real
        if not _does_user_exist(revent['Reddit Username']):
            continue

        revent['Start Time'] = start_datetime
        if revent['End Time'] != '':
            revent['End Time'] = end_datetime

        del revent['Timestamp']
        del revent['Date']
        del revent['Reddit Username']

        events.append(revent)

    print(str(len(raw_events) - len(events)) + " events removed")

    events.sort(key=lambda x: x['Start Time'])
    return events

def _timestr(d):
    s = d.strftime('%I:%M%p')
    if s[0] == '0':
        return s[1:]
    return s

def _gen_row_elements(event):
    ''' example event
    {
        'End Time': datetime.datetime(2016, 7, 31, 1, 0),
        'Event Type': 'Lure party (3) and movie',
        'Link': 'https://www.facebook.com/events/1041516392591289/',
        'Location': 'To be decided based on poll',
        'Start Time': datetime.datetime(2016, 7, 30, 9, 0)
    }
    '''

    url = event['Link'].strip()
    if url != '' and 200 == _response_code(url):
        if 'facebook' in url:
            keyword = 'facebook'
        elif 'reddit' in url:
            keyword = 'post'
        else:
            keyword = 'link'
        url = '[' + keyword + '](' + url + ')'
    else:
        url = ''

    row = []
    row.append(event['Start Time'].strftime('%a %b %d'))
    row.append(event['Event Type'])
    row.append(_timestr(event['Start Time']) + ' - ' + _timestr(event['End Time']))
    row.append(event['Location'])
    row.append(url)

    return row

def _create_table(events):
    rows = []
    rows.append(['Day', 'Type', 'Time', 'Location', 'Link'])
    rows.append(['---'] * 5)
    rows += list(map(_gen_row_elements, events))

    #Convert to string rows
    strrows = []
    for row in rows:
        strrow = ' | '.join(row)
        strrow.strip()
        strrows.append(strrow)

    return '\n'.join(strrows)

def _gen_post(events):
    current_time = datetime.datetime.now()
    table = _create_table(events)

    post = '**To have your event added please fill out [this form](http://goo.gl/forms/f0fWwjTa7oOgsYIs1) and it will be included ASAP**\n\n'
    post += table
    post += '\n\n**Last Updated: ' + current_time.strftime('%I:%M %p %m/%d') + '**'

    return post

def get_post(use_cache=True):
    updated, sheet = _get_sheet()
    if use_cache and not updated and isfile('post.txt'):
        f = open('post.txt', 'r')
        post = f.read()
        f.close()
    else:
        post = _gen_post(_get_events(sheet))
        f = open('post.txt', 'w')
        f.write(post)
        f.close()

    return post

if __name__ == '__main__':
    get_post(False)
