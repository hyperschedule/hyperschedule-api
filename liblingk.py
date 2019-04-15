"""
Module for retrieving data from the HMC Lingk API and turning the
subset that is useful to us (i.e. course descriptions) into a somewhat
more sane format. Main entry point is get_lingk_course_description_index.

Much of this logic was cribbed from
<https://github.com/hmc-portal2/hmc-scheduler/blob/681927466a5927f2e5b3f3461d02fc7ea36fafec/portal-scraper/scrape.py>
-- massive thanks to Gavin Yancey @g-rocket!
"""

import base64
import datetime
import json
import hashlib
import hmac
import urllib.parse

import requests
import requests.exceptions

import libcourse
from util import ScrapeError

LINGK_ENDPOINT = "/v1/harveymudd/coursecatalog/ps/datasets/coursecatalog"
LINGK_URL = ("https://www.lingkapis.com{}?limit=1000000000"
             .format(LINGK_ENDPOINT))

LINGK_RETRY_COUNT = 10

def get_auth_header(key, secret, date):
    message = "date: {}\n(request-target): get {}".format(date, LINGK_ENDPOINT)
    signature = base64.b64encode(
        hmac.new(bytes(secret, "ascii"), bytes(message, "ascii"),
                 digestmod=hashlib.sha1).digest())
    attrs = {
        "keyId": key,
        "algorithm": "hmac-sha1",
        "headers": "date (request-target)",
        "signature": urllib.parse.quote(signature),
    }
    return "Signature {}".format(
        ",".join('{}="{}"'.format(key, val) for key, val in attrs.items()))

def get_lingk_data(key, secret):
    # For some bizarre reason the Lingk API sometimes returns 401
    # Unauthorized even when you are authenticated correctly. Asking
    # again a few times fixes the issue. I don't even want to know
    # why.
    last_error = None
    for i in range(LINGK_RETRY_COUNT):
        now = datetime.datetime.utcnow()
        date = now.strftime("%a, %d %b %Y %H:%M:%S UTC")
        response = requests.get(LINGK_URL, headers={
            "Date": date,
            "Authorization": get_auth_header(key, secret, date)
        })
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            last_error = e
            continue
        except ValueError:
            raise ScrapeError("Lingk API returned no data")
        except json.decoder.JSONDecodeError:
            raise ScrapeError("Lingk API did not return valid JSON")
    raise ScrapeError(
        "Lingk API returned error response: {}".format(last_error))

def lingk_data_to_course_descriptions(data, lingk_term):
    if not isinstance(data, dict):
        raise ScrapeError("Lingk JSON is not map")
    if "data" not in data:
        raise ScrapeError("Lingk JSON is missing 'data' field")
    desc_index = {}
    for idx, course in enumerate(data["data"]):
        if "description" not in course:
            continue
        description = course["description"]
        if not isinstance(description, str):
            raise ScrapeError(
                "'description' at index {} is not string".format(idx))
        if "courseNumber" not in course:
            raise ScrapeError(
                "Lingk JSON at index {} is missing 'courseNumber' field"
                .format(idx))
        course_code = course["courseNumber"]
        # Special case that doesn't show up on Portal.
        if course_code == "ABROAD   HM":
            continue
        partial_course = libcourse.parse_claremont_course_code(course_code)
        # We want to use the index key representation, but this only
        # works if there's a section number rather than None. We'll
        # have to change the section number of actual courses to 0 to
        # look them up against this index. Inelegant but works for
        # now.
        partial_course["section"] = 0
        index_key = libcourse.course_to_index_key(partial_course)
        if index_key in desc_index and desc_index[index_key] != description:
            raise ScrapeError("Lingk JSON has duplicate course: {}".format(
                libcourse.format_course(partial_course)))
        desc_index[index_key] = description
    return desc_index

def get_lingk_course_description_index(key, secret, term):
    data = get_lingk_data(key, secret)
    return lingk_data_to_course_descriptions(
        data, libcourse.format_term(term))
