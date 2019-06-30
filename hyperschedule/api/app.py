"""
Module containing the Hyperschedule backend Flask app.
"""

import functools

import flask
import flask_cors

import hyperschedule
import hyperschedule.api.database
import hyperschedule.api.notify
import hyperschedule.api.validate

from hyperschedule.api.util import UserError
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

def api_response(data):
    """
    Return a JSONified API response from the given dictionary.
    """
    return flask.jsonify({
        "error": None,
        **data,
    })

@app.errorhandler(UserError)
def handle_user_error(error):
    """
    Return a JSONified API error response with the given error
    message.
    """
    if error.code is Unset:
        return flask.jsonify({
            "error": str(error),
        })
    else:
        return str(error), error.code

@app.route("/")
def view_index():
    """
    View for the index page redirecting users to
    https://hyperschedule.io.
    """
    return flask.send_from_directory(
        hyperschedule.ROOT_DIR, "html/index.html")

@app.route("/health-check")
def view_health_check():
    """
    View for the ELB health check.
    """
    return "", 204

@app.route("/api/v4/courses")
@nocache
def view_api_v4_get():
    """
    View for the Hyperschedule API used by the frontend to retrieve
    course information.
    """
    scraper = flask.request.args.get("scraper", Unset)
    if scraper is Unset:
        raise UserError("request failed to specify scraper")
    current_term = flask.request.args.get("currentTerm", Unset)
    requested_term = flask.request.args.get("requestedTerm", Unset)
    since = flask.request.args.get("since", Unset)
    if since is not Unset:
        try:
            since = int(since)
        except (TypeError, ValueError):
            raise UserError("timestamp is not an integer: {}".format(since))
    if since is not Unset and current_term is Unset:
        raise UserError("incremental update requires specifying current term")
    data, full, until, term = app.database.get_diff_to_present(
        scraper_id=scraper, since=since,
        current_term_code=current_term, requested_term_code=requested_term,
    )
    if data is Unset:
        raise UserError("data not available yet", code=503)
    return api_response({
        "courses": data,
        "until": until,
        "full": full,
        "term": term,
    })

@app.route("/api/v4/courses", methods=["POST"])
def view_api_v4_post():
    """
    View for the Hyperschedule API used by the scrapers to update
    course data.
    """
    hyperschedule.api.validate.check(flask.request.json)
    scraper_id = flask.request.json["scraper"]
    term_data = flask.request.json["term"]
    courses = flask.request.json["courses"]
    app.database.set_current_data(scraper_id, term_data, courses)
    hyperschedule.api.notify.report_success()
    return api_response({})

app.database = hyperschedule.api.database.Database()
