smscal
======

Text today's events from a Google Calendar account to a phone number.


Heroku services required include Mongolab and Scheduler, SSL is recommended.

Google client ID and secrets should be stored as heroku config vars:

    heroku config:add GOOGLE_CLIENT_ID=abc GOOGLE_CLIENT_SECRET=123
    heroku config:add GOOGLE_REDIRECT_URI=https://example.com/oauth2callback

Twilio credentials also to be stored as config vars:

    heroku config:add TWILIO_ACCOUNT=123 TWILIO_TOKEN=abc
