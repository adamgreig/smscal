import os
import sys
import json
import flask
import urllib
import hashlib
import pymongo
import requests
import datetime
import dateutil.parser

app = flask.Flask(__name__)

def config_var(var):
    try:
        return os.environ[var]
    except KeyError:
        print "Could not find {0} in env, quitting.".format(var)
        sys.exit(1)

def md5(string):
    return hashlib.md5(string).hexdigest()

def setup_mongo():
    uri = config_var('MONGOLAB_URI')
    dbname = uri.split('/')[-1]
    con = pymongo.Connection(uri)
    db = con[dbname]
    return db

db = setup_mongo()

def auth_url():
    url = "https://accounts.google.com/o/oauth2/auth"
    scope_user = "https://www.googleapis.com/auth/userinfo.profile"
    scope_cal = "https://www.googleapis.com/auth/calendar.readonly"
    params = {
        'response_type': 'code',
        'client_id': config_var('GOOGLE_CLIENT_ID'),
        'redirect_uri': config_var('GOOGLE_REDIRECT_URI'),
        'scope': '{0} {1}'.format(scope_cal, scope_user),
        'access_type': 'offline',
        'approval_prompt': 'force'
    }
    return "{0}?{1}".format(url, urllib.urlencode(params))

def code_for_token(code):
    url = "https://accounts.google.com/o/oauth2/token"
    params = {
        'code': code,
        'client_id': config_var('GOOGLE_CLIENT_ID'),
        'client_secret': config_var('GOOGLE_CLIENT_SECRET'),
        'redirect_uri': config_var('GOOGLE_REDIRECT_URI'),
        'grant_type': 'authorization_code'
    }
    r = requests.post(url, data=params)
    results = json.loads(r.text)
    access_token = results['access_token']
    refresh_token = results['refresh_token']
    return (access_token, refresh_token)

def refresh_token(refresh_token):
    url = "https://accounts.google.com/o/oauth2/token"
    params = {
        'refresh_token': refresh_token,
        'client_id': config_var('GOOGLE_CLIENT_ID'),
        'client_secret': config_var('GOOGLE_CLIENT_SECRET'),
        'grant_type': 'refresh_token'
    }
    r = requests.post(url, data=params)
    results = json.loads(r.text)
    return results['access_token']

def get_profile(access_token):
    url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': access_token}
    r = requests.get(url, params=params)
    return json.loads(r.text)

def get_calendars(access_token):
    url = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
    params = {'access_token': access_token}
    r = requests.get(url, params=params)
    result = json.loads(r.text)
    cals = []
    for item in result['items']:
        cal = {'id': item['id'], 'active': False}
        if 'summaryOverride' in item:
            cal['name'] = item['summaryOverride']
        else:
            cal['name'] = item['summary']
        cals.append(cal)
    return cals

def get_todays_events(access_token, cal_id):
    url = "https://www.googleapis.com/calendar/v3/calendars/{0}/events"
    url = url.format(urllib.quote_plus(cal_id))
    params = {
        'access_token': access_token,
        'orderBy': 'startTime',
        'singleEvents': 'true',
        'timeMin': datetime.datetime.now().strftime("%Y-%m-%dT00:00:00Z"),
        'timeMax': datetime.datetime.now().strftime("%Y-%m-%dT23:59:59Z")
    }
    url = "{0}?{1}".format(url, urllib.urlencode(params))
    r = urllib.urlopen(url)
    results = json.loads(r.read())
    events = []
    if 'items' not in results:
        return events
    for item in results['items']:
        if 'date' in item['start']:
            time = -1
        else:
            start = dateutil.parser.parse(item['start']['dateTime'])
            if start.minute == 0:
                time = start.strftime("%H")
            else:
                time = start.strftime("%H.%M")
        name = item['summary']
        events.append((time, name))
    return events

def events_to_texts(events):
    events = ["{0}: {1}".format(*e) if e[0] != -1 else e[1] for e in events]
    build = "Today: {0}".format(events[0])
    texts = []
    for event in events[1:]:
        if len(build) + len(event) > 158:
            texts.append(build)
            build = event
        else:
            build += ", {0}".format(event)
    return texts + [build]

def send_text(number, message):
    url = "https://api.twilio.com/2010-04-01/Accounts/{0}/SMS/Messages"
    url = url.format(config_var('TWILIO_ACCOUNT'))
    params = {'From': config_var('TWILIO_NUMBER'),
            'To': number, 'Body': message}
    requests.post(url, data=params, auth=(config_var('TWILIO_ACCOUNT'),
                      config_var('TWILIO_TOKEN')))

@app.route('/')
def index():
    return flask.render_template('index.html', url=auth_url())

@app.route('/oauth2callback')
def oauth2callback():
    args = flask.request.args
    if args.get('error', None):
        return "Authentication error: {0}".format(args['error'])
    code = args.get('code', None)
    if not code:
        return "Authentication error: no code provided"
    tokens = code_for_token(code)
    cals = get_calendars(tokens[0])
    profile = get_profile(tokens[0])
    user_id = profile['id']
    doc = {'_id': user_id, 'profile': profile, 'refresh_token': tokens[1],
           'cals': dict((md5(c['id']), c) for c in cals)}
    db.users.save(doc)
    return flask.render_template('pick_cals.html', cals=cals, user_id=user_id)

@app.route('/setup', methods=['POST'])
def setup():
    form = flask.request.form
    doc = db.users.find_one(form['user_id'])
    if not doc:
        return "User data not found. Please try again."
    for k, v in form.iteritems():
        if k == 'user_id':
            continue
        elif k == 'number':
            doc['number'] = v
        elif k == 'hour':
            doc['hour'] = v
        elif v == 'on':
            try:
                doc['cals'][md5(k)]['active'] = True
            except KeyError:
                doc['cals'][md5(k)] = {'active': True, 'id': k}
    db.users.save(doc)
    return "Settings saved!"

@app.route('/cron')
def cron():
    current_hour = datetime.datetime.now().hour
    for user in db.users.find():
        if int(user['hour']) == int(current_hour):
            user_events = []
            access_token = refresh_token(user['refresh_token'])
            for cal in user['cals'].itervalues():
                if cal['active']:
                    user_events += get_todays_events(access_token, cal['id'])
            user_events.sort()
            texts = events_to_texts(user_events)
            for text in texts:
                send_text(user['number'], text)
    return "OK"


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
