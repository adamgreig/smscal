import os
import sys
import flask
import pymongo

def setup_mongo():
    try:
        uri = os.environ['MONGOLAB_URI']
        dbname = uri.split('/')[-1]
        print "Trying URI {0} and DB {1}...".format(uri, dbname)
        con = pymongo.Connection(uri)
        db = con[dbname]
    except KeyError:
        print "Could not find MONGOLAB_URI in env, quitting."
        sys.exit(1)
    return db

app = flask.Flask(__name__)
db = setup_mongo()

@app.route('/')
def index():
    return flask.render_template('index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
