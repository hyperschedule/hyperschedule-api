"""
Module containing the Hyperschedule backend Flask app.
"""

import os
import functools

import flask
import flask_cors

import hyperschedule
import hyperschedule.worker as worker
import hyperschedule.database_worker as database_worker

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
    return flask.jsonify({"error": None, **data,})


@app.errorhandler(APIError)
def handle_api_error(error):
    """
    Return a JSONified API error response with the given error
    message.
    """
    return flask.jsonify({"error": str(error),})


@app.route("/")
def view_index():
    """
    View for the index page redirecting users to
    https://hyperschedule.io.
    """
    return flask.send_from_directory(hyperschedule.ROOT_DIR, "html/index.html")


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

@app.route("/upload-syllabus", methods = ['PUT', 'POST', 'OPTIONS'])
@nocache
def upload_syllabus():
    """
    A post method to upload course syllabus. The POST method requires a token
    and a syllabus pdf. It uploads the syllabus to Firebase and return success
    or failure.
    """
    token = flask.request.form.get('token')
    if token is None:
        raise APIError("user token not provided")
    course_code = flask.request.form.get('courseCode')
    if course_code is None:
        raise APIError("course code is not provided")
    syllabus_date = flask.request.form.get('syllabusDate')
    if syllabus_date is None:
        raise APIError("syllabus date is not provided")
    pdf = flask.request.files['pdf']
    if pdf is None or pdf.filename is '':
        raise APIError("pdf file not provided")

    result = database_worker.upload_to_cloud_storage(token, course_code, syllabus_date, pdf)
    return api_response({"success": result})
    

app.worker = worker.HyperscheduleWorker()
app.worker.start()
