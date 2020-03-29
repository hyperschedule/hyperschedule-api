"""
Module for retrieving data from the HMC Lingk API (or a hacky CSV
that the registrar gave me which is now on Google Drive) and
extracting course descriptions from the result.

Main entry point is `get_course_descriptions`.

Much of this logic was cribbed from
<https://github.com/hmc-portal2/hmc-scheduler/blob/681927466a5927f2e5b3f3461d02fc7ea36fafec/portal-scraper/scrape.py>
-- massive thanks to Gavin Yancey @g-rocket!
"""

import base64
import csv
import datetime
import json
import hashlib
import hmac
import os
import pathlib
import re
import shutil
import tempfile
import time
import urllib.parse
import zipfile

import requests
import requests.exceptions

import hyperschedule.scrapers.claremont.shared as shared
import hyperschedule.util as util

from hyperschedule.util import ScrapeError

# Lingk API endpoint used to get course data.
#
# This is factored out as a constant because it is used to compute the
# authentication header.
LINGK_ENDPOINT = "/v1/harveymudd/coursecatalog/ps/datasets/coursecatalog"

# Full URL to Lingk API endpoint used to get course data.
LINGK_URL = f"https://www.lingkapis.com{LINGK_ENDPOINT}?limit=1000000000"

# Full URL to download hacky Lingk CSV file that the registrar gave
# me.
LINGK_ZIP_ID = "1DMHoyIvQthANjqO1DIv78lmWp4b8WDCp"
LINGK_ZIP_URL = f"https://drive.google.com/uc?export=download&id={LINGK_ZIP_ID}"


# Number of times to retry getting data from the Lingk API if it
# returns a spurious authentication error.
LINGK_RETRY_COUNT = 10


def get_auth_header(key, secret, date):
    """
    Return a string that can be used as an HTTP Authorization header
    for the Lingk API, given a Lingk API key and secret as well as a
    string representing the current timestamp in the appropriate
    format.
    """
    message = f"date: {date}\n(request-target): get {LINGK_ENDPOINT}"
    signature = base64.b64encode(
        hmac.new(
            bytes(secret, "ascii"), bytes(message, "ascii"), digestmod=hashlib.sha1
        ).digest()
    )
    attrs = {
        "keyId": key,
        "algorithm": "hmac-sha1",
        "headers": "date (request-target)",
        "signature": urllib.parse.quote(signature),
    }
    return "Signature {}".format(
        ",".join(f'{key}="{val}"' for key, val in attrs.items())
    )


def get_lingk_api_data(key, secret):
    """
    Return the decoded JSON response from the Lingk API, using the
    given key and secret for authentication.

    Throw ScrapeError if the API is not available or returns bad data.
    """
    # For some bizarre reason the Lingk API sometimes returns 401
    # Unauthorized even when you are authenticated correctly. Asking
    # again a few times fixes the issue. I don't even want to know
    # why.
    last_error = None
    fails = 0
    for i in range(LINGK_RETRY_COUNT):
        now = datetime.datetime.utcnow()
        date = now.strftime("%a, %d %b %Y %H:%M:%S UTC")
        response = requests.get(
            LINGK_URL,
            headers={"Date": date, "Authorization": get_auth_header(key, secret, date)},
        )
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            fails += 1
            util.log_verbose(
                f"Got auth error from Lingk API ({fails} of {LINGK_RETRY_COUNT} allowed)"
            )
            time.sleep(1)
            last_error = e
            continue
        except ValueError:
            raise ScrapeError("Lingk API returned no data")
        except json.decoder.JSONDecodeError:
            raise ScrapeError("Lingk API did not return valid JSON")
    raise ScrapeError(f"Lingk API returned error response: {last_error}")


def lingk_api_data_to_course_descriptions(data):
    """
    Given the decoded JSON from the Lingk API, return a dictionary
    mapping tuples of course information (`with_section` false; see
    `shared.course_info_as_list`) to course descriptions.

    Throw ScrapeError if the data is malformed.
    """
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
            raise ScrapeError(f"'description' at index {idx} is not string")
        if "courseNumber" not in course:
            raise ScrapeError(
                f"Lingk JSON at index {idx} is missing 'courseNumber' field"
            )
        course_code = course["courseNumber"]
        # Special case that doesn't show up on Portal.
        if course_code == "ABROAD   HM":
            continue
        course_info = shared.parse_course_code(course_code, with_section=False)
        course_key = tuple(shared.course_info_as_list(course_info, with_section=False))
        found_mismatch = (
            course_key in desc_index and desc_index[course_key] != description
        )
        if found_mismatch:
            raise ScrapeError(f"Lingk JSON has duplicate course: {course_key!r}")
        desc_index[course_key] = description
    return desc_index


def get_lingk_csv_data():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = pathlib.Path(tmp_dir)
        zip_file = tmp_dir / "HMCarchive-Spring2020.zip"
        with requests.get(LINGK_ZIP_URL, stream=True) as r:
            with open(zip_file, "wb") as f:
                shutil.copyfileobj(r.raw, f)
        with zipfile.ZipFile(zip_file) as zip_file:
            with zip_file.open("course_1.csv") as f:
                # Unfortunately, we have to read the whole file into
                # memory because the way the file is split into lines
                # is wrong and needs to be adjusted in some places.
                #
                # I used Chared to detect the encoding
                # <https://nlp.fi.muni.cz/projects/chared/>. But even
                # so, there are still corrupted bytes.
                contents = f.read().decode(encoding="cp1252", errors="replace")
    # CSV contains unescaped double quotes inside quoted literals,
    # naturally. Also, these unescaped double quotes appear next to
    # commas and newlines, making it next to impossible to fix them
    # automatically. Hence the following *absolutely horrifying* hack.
    contents = re.sub(
        r'"([A-Z]{2})","\1","(.*?)"(?=\n[^\n]+"([A-Z]{2})","\3")',
        (
            lambda m: '"{}","{}","{}"'.format(
                m.group(1), m.group(1), re.sub(r'"', '""', m.group(2))
            )
        ),
        contents,
        flags=re.DOTALL,
    )
    return list(csv.reader(contents.splitlines()))


def lingk_csv_data_to_course_descriptions(data):
    header, *rows = data
    try:
        course_code_idx = header.index("courseNumber")
        desc_idx = header.index("description")
    except ValueError:
        raise ScrapeError(f"unexpected header: {header!r}") from None
    desc_map = {}
    for row in rows:
        # We have some rows that are completely empty and some that
        # are just whitespace.
        if not row or "".join(row).isspace():
            continue
        if len(row) != len(header):
            raise ScrapeError(f"malformed row: {row!r}")
        course_code = row[course_code_idx]
        try:
            course_info = shared.parse_course_code(course_code, with_section=False)
        except ScrapeError:
            continue
        index_key = tuple(shared.course_info_as_list(course_info, with_section=False))
        description = row[desc_idx]
        if not description:
            continue
        description = " ".join(description.split())
        # If two conflicting descriptions for the same course code
        # (yep, it happens), pick the one that comes later :/
        desc_map[index_key] = description
    if len(desc_map) < 100:
        raise ScrapeError(f"Not enough course descriptions: {len(desc_map)}") from None
    return desc_map


def get_course_descriptions():
    """
    Given a Lingk API key and secret for authentication, return a
    dictionary mapping course codes (as can be used on the frontend)
    to course descriptions.

    Throw ScrapeError if the API is not available or returns bad data.
    """
    if util.get_env_boolean("lingk"):
        key = os.environ.get("HYPERSCHEDULE_LINGK_KEY")
        secret = os.environ.get("HYPERSCHEDULE_LINGK_SECRET")
        if not key or not secret:
            util.log("Skipping Lingk as key and secret are not set")
            return {}
        util.log_verbose("Scraping Lingk API")
        data = get_lingk_api_data(key, secret)
        desc_index = lingk_api_data_to_course_descriptions(data)
    else:
        util.log_verbose("Scraping Lingk CSV")
        data = get_lingk_csv_data()
        desc_index = lingk_csv_data_to_course_descriptions(data)
    if len(desc_index) < 100:
        raise ScrapeError(f"Not enough course descriptions: {len(desc_index)}")
    return desc_index
