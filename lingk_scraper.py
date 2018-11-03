import re
import datetime
import requests
import hmac
import os
import base64
import urllib
from hashlib import sha1
import sys
import json

# ******************* These are copied from server.py ************************

# We will separate these into a new helper file later when we separate the
# server.py into modules.

class ScrapeError(Exception):
    pass

## Logging

def log(message):
    print("[{}] {}".format(
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        message), file=sys.stderr)

# ***************************************************************************

## Constants

BASE = 'www.lingkapis.com'
EXTENSION = '/v1/harveymudd/coursecatalog/ps/datasets/coursecatalog'

if 'KEY' in os.environ and 'SECRET' in os.environ:
    KEY = os.environ['KEY']
    SECRET = os.environ['SECRET']
else:
    raise Exception('KEY and SECRET need to be set in the environment.')

## Helpers

def time_html_format() -> str:
    return datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S UTC')

def gen_auth_header(key: str, secret: str, date_str: str) -> str:
    '''
    Returns an authentication header for HMAC-based authentication.
    Credit to Jordan R.A., Olivia Watkins, Kate Woolverton, and Gavin Yancey
    for figuring out the nuances of this awful, broken API.
    '''
    # whitespace-sensitive, requires the newline
    sig = (f'date: {date_str}\n'
           # method has to be lowercase
           f'(request-target): get ') \
           + EXTENSION
    # convert to bytes for hmac
    hashed_sig = hmac.new(bytes(secret, 'ascii'), bytes(sig, 'ascii'), sha1)
    # convert to base64
    encoded_sig = base64.b64encode(hashed_sig.digest())
    # parse into url-friendly format
    urlified_sig = urllib.parse.quote(encoded_sig)
    return (f'Signature keyId="{key}",'
            f'algorithm="hmac-sha1",'
            'headers="date (request-target)",'
            f'signature="{urlified_sig}"')

## Course data scraping

def get_course_data(key: str, secret: str, limit: int=10000,
                    iterations: int=10) -> dict:
    '''
    Returns the JSON representation of the course data.
    iterations: the number of iterations to try connecting
                (it sometimes doesn't authenticate).
    Credit to Jordan R.A., Olivia Watkins, Kate Woolverton, and Gavin Yancey
    for figuring out the nuances of this awful, broken API.
    '''
    for _ in range(iterations):
        date_str = time_html_format()
        auth_header = gen_auth_header(key, secret, date_str)
        # they want the header nested inside of this for some reason...
        headers = {'Date': date_str, 'Authorization': auth_header}
        params = {'limit': limit}
        r = requests.get(f'https://{BASE + EXTENSION}',
                         headers=headers, params=params)
        if r.status_code == requests.codes.ok:
            return r.json()['data']
    else:
        log(f'lingk scraping failed after {iterations} iterations')

# split lingk entityID to department, course_number, num_suffix, school
# 'SPAN199DRPO' => SPAN, 199, DR, PO
# 'ENGR190AKHM' => ENGR, 190, AK, HM
# 'FGSS189  SC' => FGSS, 189, , SC
COURSE_ID_REGEX = r"([A-Z]+) *([0-9]+) *([A-Z]*[0-9]?) *([A-Z]{2})"

def make_description_dict(lingk_data: list) -> dict :
    '''
    Make a dictionary that points the course key in the format
    'department/course_number/suffix/school' to the corresponding description
    string scrpaed from lingkData. The lingkData is an array of courses scraped 
    from lingk api.

    Note: if the lingkData is not properly filtered, the dict might contain everything
    since 2016.
    '''
    lingk_description_dict = {}
    for course in lingk_data :
        try:
            # Many courses in the lingk course list do not have descriptions.
            # Many of them are malformed.
            if 'description' in course :
                # There is a course in the lingk api that looks like this:
                # "externalId": "\n\"FGSS189  SC" this line is just to account
                # for that.
                rawstr = course['externalId'].strip().strip('\"')

                match = re.match(COURSE_ID_REGEX, rawstr)
                if not match :
                    raise ScrapeError("\"%s\" : lingk malformed course, string not match" % rawstr)
                department, course_number, num_suffix, school = match.groups()
                hyperscheduleKey = '/'.join([department, course_number, num_suffix, school])
                # course description from lingk sometimes have multiple newlines
                description = course['description'].strip()
                if hyperscheduleKey in lingk_description_dict :
                    raise ScrapeError("%s : lingk duplicate course key" % hyperscheduleKey)
                lingk_description_dict[hyperscheduleKey] = description
        except Exception as e:
            log(type(e).__name__ + " " + "Exception:" + " " + str(e))
    return lingk_description_dict

def fetch_and_process_description_dict():
    lingk_course_data = get_course_data(KEY, SECRET)
    description_dict = make_description_dict(lingk_course_data)
    return description_dict

COURSE_INDEX_ATTRS_FOR_LINGK_DICT = (
    "department",
    "courseNumber",
    "courseCodeSuffix",
    "school",
)

def course_to_lingk_description_dict_key(course):
    return "/".join(str(course[attr]) for attr in COURSE_INDEX_ATTRS_FOR_LINGK_DICT)

# Driver function for testing
if __name__ == '__main__' :
    description_dict = fetch_and_process_description_dict()
    for i, key in zip(range(20), description_dict):
        print(key)
        print(description_dict[key])



