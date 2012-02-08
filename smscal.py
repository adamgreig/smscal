import os
import sys
import json
import flask
import urllib
import pymongo
import requests

app = flask.Flask(__name__)

def config_var(var):
    try:
        return os.environ[var]
    except KeyError:
        print "Could not find {0} in env, quitting.".format(var)
        sys.exit(1)

def setup_mongo():
    uri = config_var('MONGOLAB_URI')
    dbname = uri.split('/')[-1]
    con = pymongo.Connection(uri)
    db = con[dbname]
    return db

def auth_url():
    url = "https://accounts.google.com/o/oauth2/auth"
    params = {
        'response_type': 'code',
        'client_id': config_var('GOOGLE_CLIENT_ID'),
        'redirect_uri': config_var('GOOGLE_REDIRECT_URI'),
        'scope': 'https://www.googleapis.com/auth/calendar.readonly',
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
    r = requests.get(url, params=params)
    results = json.loads(r.text)
    return results['access_token']

def get_calendars(access_token):
    url = "https://googleapis.com/calendar/v3/users/me/calendarList"
    params = {'access_token': access_token}
    r = requests.get(url, params=params)
    result = json.loads(r.text)
    cals = []
    for item in result['items']:
        cal = {'id': item['id']}
        if item['summaryOverride']:
            cal['name'] = item['summaryOverride']
        else:
            cal['name'] = item['summary']
        cals.append(cal)
    return cals

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
    return flask.render_template('pick_cals.html', access_token=tokens[0],
                                  refresh_token=tokens[1], cals=cals)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
