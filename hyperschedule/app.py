"""
Module containing the Hyperschedule backend Flask app.
"""

import functools

import flask
import flask_cors

import hyperschedule
import hyperschedule.worker as worker

from hyperschedule.util import Unset

# Hyperschedule Flask app.
app = flask.Flask("hyperschedule")
flask_cors.CORS(app)

# <http://librelist.com/browser/flask/2011/8/8/add-no-cache-to-response/#952cc027cf22800312168250e59bade4>
def nocache(f):
    """
    Decorator for a Flask view that disables caching.
    """
    def new_func(*args, **kwargs):
        resp = flask.make_response(f(*args, **kwargs))
        resp.cache_control.no_cache = True
        return resp
    return functools.update_wrapper(new_func, f)

class APIError(Exception):
    """
    Exception that is turned into an error response from the API.
    """

    pass

def api_response(data):
    """
    Return a JSONified API response from the given dictionary.
    """
    return flask.jsonify({
        "error": None,
        **data,
    })

@app.errorhandler(APIError)
def handle_api_error(error):
    """
    Return a JSONified API error response with the given error
    message.
    """
    return flask.jsonify({
        "error": str(error),
    })

@app.route("/")
def view_index():
    """
    View for the index page redirecting users to
    https://hyperschedule.io.
    """
    return flask.send_from_directory(
        hyperschedule.ROOT_DIR, "html/index.html")

@app.route("/api/v3/courses")
@nocache
def view_api_v3():
    """
    View for the Hyperschedule API used by the frontend to retrieve
    course information.
    """
    school = flask.request.args.get("school")
    if not school:
        raise APIError("request failed to specify school")
    if school not in ("cmc", "hmc", "pitzer", "pomona", "scripps"):
        raise APIError("unknown school: {}".format(repr(school)))
    since = flask.request.args.get("since")
    if not since:
        until, data = app.worker.get_current_data()
        if data is Unset:
            raise APIError("data not available yet")
        return api_response({"data": data, "until": until, "full": True})
    try:
        since = int(since)
    except ValueError:
        raise APIError("'since' not an integer: {}".format(repr(since)))
    diff, full, until = app.worker.get_diff_to_present(since)
    if diff is Unset:
        raise APIError("data not available yet")
    return api_response({"data": diff, "until": until, "full": full})

app.worker = worker.HyperscheduleWorker()
app.worker.start()
