"""
Module for retrieving data from the HMC Lingk API (or a hacky CSV
that the registrar gave me which is on Google Drive) and turning the
subset that is useful to us (i.e. course descriptions) into a somewhat
more sane format. Main entry point is
get_lingk_course_description_index.

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
import urllib.parse
import zipfile

import requests
import requests.exceptions

import hyperschedule.libcourse as libcourse
from hyperschedule.util import ScrapeError

LINGK_ENDPOINT = "/v1/harveymudd/coursecatalog/ps/datasets/coursecatalog"
LINGK_URL = ("https://www.lingkapis.com{}?limit=1000000000"
             .format(LINGK_ENDPOINT))
LINGK_ZIP_URL = ("https://drive.google.com/uc?export=download&id={}"
                 .format("1rBLpKPamVzHUQ8UjgmkSqSaVsT7KeT6m"))

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

def get_lingk_api_data(key, secret):
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

def lingk_api_data_to_course_descriptions(data, lingk_term):
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

def get_lingk_drive_data():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = pathlib.Path(tmp_dir)
        zip_file = tmp_dir / "HMCarchive.zip"
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
        (lambda m:
         '"{}","{}","{}"'.format(
             m.group(1), m.group(1), re.sub(r'"', '""', m.group(2)))),
        contents,
        flags=re.DOTALL)
    return list(csv.reader(contents.splitlines()))

def lingk_drive_data_to_course_descriptions(data, term):
    header, *rows = data
    try:
        course_code_idx = header.index("courseNumber")
        desc_idx = header.index("description")
    except ValueError:
        raise ScrapeError(
            "unexpected header: {}".format(repr(header))) from None
    desc_map = {}
    for row in rows:
        # We have some rows that are completely empty and some that
        # are just whitespace.
        if not row or "".join(row).isspace():
            continue
        if len(row) != len(header):
            raise ScrapeError("malformed row: {}".format(repr(row)))
        course_code = row[course_code_idx]
        try:
            partial_course = libcourse.parse_claremont_course_code(course_code)
        except ScrapeError:
            continue
        partial_course["section"] = 0
        index_key = libcourse.course_to_index_key(partial_course)
        description = row[desc_idx]
        if not description:
            continue
        description = " ".join(description.split())
        if index_key in desc_map:
            # If two conflicting descriptions for the same course code
            # (yep, it happens), pick whichever one is longer :/
            description = max(description, desc_map[index_key], key=len)
        desc_map[index_key] = description
    if len(desc_map) < 100:
        raise ScrapeError(
            "Not enough course descriptions: {}"
            .format(len(desc_map))) from None
    return desc_map

def get_lingk_course_description_index(key, secret, term):
    if key and secret and os.environ.get("HYPERSCHEDULE_LINGK_ENABLE"):
        data = get_lingk_api_data(key, secret)
        return lingk_api_data_to_course_descriptions(
            data, libcourse.format_term(term))
    else:
        data = get_lingk_drive_data()
        return lingk_drive_data_to_course_descriptions(
            data, libcourse.format_term(term))
