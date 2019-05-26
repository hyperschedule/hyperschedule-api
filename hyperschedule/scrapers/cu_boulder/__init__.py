"""
Course scraper for the University of Colorado at Boulder. Uses
data from the <https://classes.colorado.edu/> API.

Basic course information is easily available in JSON format, but more
detailed information requires making one API request per class.
Therefore this scraper is designed to retrieve detailed information
for only a small number of classes each time it is invoked, and to
pick up where it left off.

We key the courses by CRN (Course Reference Number), since it is
necessary to provide the CRN to get all the information about a course
(the course code is insufficient). Also, in this API, terms are
represented by 'srcdb' numbers.

As a further point of unintuitiveness, despite the fact that a CRN is
all that is necessary to uniquely identify a course, providing the
course code is also required to get a full response from the API.
"""

import argparse
import json
import random
import re
import sys
import threading
import time
import traceback

import bs4
import requests

from hyperschedule.util import Unset


def srcdb_info_key(srcdb_info):
    """
    Return the sort key to use for srcdb maps parsed from the course
    search JavaScript.
    """
    match = re.fullmatch(r"(Fall|Spring) (\d{4})", srcdb_info["name"])
    if not match:
        return (False,)
    semester, year = match.groups()
    return (int(year), semester == "Fall")


def get_current_term():
    """
    Return a tuple of (srcdb, term). `srcdb` can be used to identify
    the term in the CU Boulder API, while `term` is a term object that
    can be used in the Hyperschedule API.
    """
    url = "https://classes.colorado.edu/"
    resp = requests.get(url)
    resp.raise_for_status()
    # Grab information about terms out of the JavaScript code embedded
    # on the home page, as it's not returned from the API.
    match = re.search(r"srcDBs: (.+),\n", resp.text)
    srcdbs_info = json.loads(match.group(1))
    srcdb_info = max(srcdbs_info, key=srcdb_info_key)
    term_name = srcdb_info["name"]
    return srcdb_info["code"], {
        "termCode": term_name,
        "termSortKey": srcdb_info_key(srcdb_info),
        "termName": term_name,
    }


def api_get_courses(srcdb):
    """
    Return the API response for a search for all CU Boulder courses.
    """
    url = "https://classes.colorado.edu/api/?page=fose&route=search"
    data = {
        "other": {
            "srcdb": srcdb,
        },
        "criteria": []
    }
    resp = requests.post(url, json=data)
    resp.raise_for_status()
    return resp.json()


def api_get_course(srcdb, crn, code):
    """
    Given a CU Boulder course code and CRN, return the API response
    for details on that course (including its sections).
    """
    url = "https://classes.colorado.edu/api/?page=fose&route=details"
    data = {
        "group": "code:{}".format(code),
        "key": "crn:{}".format(crn),
        "srcdb": srcdb,
    }
    resp = requests.post(url, json=data)
    resp.raise_for_status()
    return resp.json()


def get_available_courses(srcdb):
    """
    Return CRNs for all the CU Boulder courses currently available.
    The format is a dictionary mapping CRNs to course codes.
    """
    resp = api_get_courses(srcdb)
    return {course["crn"]: course["code"] for course in resp["results"]}


def html_to_text(html):
    """
    Given a string of HTML, return only its textual content.
    """
    return bs4.BeautifulSoup(html, "lxml").get_text()


def parse_cu_location(meeting_html):
    """
    Parse the course meeting location out of the meeting_html field of
    a CU course.
    """
    if not meeting_html.startswith("<"):
        return meeting_html
    text = html_to_text(meeting_html)
    match = re.match(r".+? in (.+)", text)
    if match:
        return match.group(1)
    match = re.match(r".+?; (.+)", text)
    if match:
        return match.group(1)
    assert False, repr(meeting_html)


def parse_cu_dates(cu_dates):
    """
    Parse the starting and ending dates out of the dates_html field of
    a CU course.
    """
    date_regex = r"\d{4}-\d{2}-\d{2}"
    match = re.fullmatch(
        r"({date}) through ({date})".format(date=date_regex), cu_dates
    )
    return match.groups()


def parse_cu_time(cu_time):
    """
    Parse times given in hhmm or hmm format into the hh:mm format used
    by Hyperschedule.
    """
    hours, minutes = cu_time[:-2], cu_time[-2:]
    return "{:02d}:{:02d}".format(int(hours), int(minutes))


def parse_cu_instructors(instructor_html):
    """
    Parse a list of instructor names out of the instructordetail_html
    field of a CU course.
    """
    return html_to_text(instructor_html).splitlines()


def parse_cu_seats(cu_seats):
    """
    Parse the total and available number of seats as well as the
    waitlist length (or null) out of the seats field of a CU course.
    """
    matches = re.findall(r"\d+", cu_seats)
    if "Waitlist" not in cu_seats:
        matches.append(None)
    if "of" in cu_seats:
        matches.pop()
    assert len(matches) == 3, repr(cu_seats)
    seats_total, seats_avail, waitlist_len = matches
    seats_total = int(seats_total)
    seats_avail = seats_total - int(seats_avail)
    if isinstance(waitlist_len, str):
        waitlist_len = int(waitlist_len)
    return seats_total, seats_avail, waitlist_len


def parse_cu_course_status(sections_html, this_crn):
    """
    Parse the current course status (e.g. open, waitlisted) out of the
    all_sections field of a CU course.
    """
    text = html_to_text(sections_html)
    for crn, status in re.findall(
            r"Nbr:\s*([0-9]+).*?Status:\s*([A-Z][a-z]*)", text
    ):
        if crn == this_crn:
            return status.lower()
    assert False


def convert_course(cu_course, term_data):
    """
    Given some course data in the format returned by the CU Boulder
    API, and a term in the format of the Hyperschedule API, convert
    the course data to the format used by the Hyperschedule API.
    """
    crn = cu_course["crn"]
    cu_section = Unset
    for cu_section in cu_course["allInGroup"]:
        if cu_section["crn"] == crn:
            break
    assert cu_section is not Unset
    start_date, end_date = parse_cu_dates(cu_course["dates_html"])
    if cu_course["meeting_html"]:
        location = parse_cu_location(cu_course["meeting_html"])
    else:
        location = None
    schedule = []
    # Yes, the API really returns a stringified JSON blob with
    # different key naming conventions inside the JSON. Perhaps for
    # similar reasons that it returns HTML strings inside the JSON.
    for cu_meeting in json.loads(cu_section["meetingTimes"]):
        days = "MTWRFSU"[int(cu_meeting["meet_day"])]
        start_time = parse_cu_time(cu_meeting["start_time"])
        end_time = parse_cu_time(cu_meeting["end_time"])
        schedule.append({
            "scheduleDays": days,
            "scheduleStartTime": start_time,
            "scheduleEndTime": end_time,
            "scheduleStartDate": start_date,
            "scheduleEndDate": end_date,
            "scheduleTermCount": 1,
            "scheduleTerms": [0],
            "scheduleLocation": location,
        })
    cu_course_code = cu_course["code"]
    section = cu_course["section"]
    course_code = cu_course_code + " " + section
    course_name = cu_course["title"]
    description = cu_course["description"]
    if cu_course["instructordetail_html"]:
        instructors = parse_cu_instructors(cu_course["instructordetail_html"])
    else:
        instructors = ["TBD"]
    num_credits = str(float(cu_course["hours"] or "0"))
    seats_total, seats_filled, waitlist_length = (
        parse_cu_seats(cu_course["seats"])
    )
    enrollment_status = parse_cu_course_status(cu_course["all_sections"], crn)
    return {
        "courseCode": course_code,
        "courseName": course_name,
        "courseSortKey": course_code,
        "courseMutualExclusionKey": cu_course_code,
        "courseDescription": description,
        "courseInstructors": instructors,
        "courseTerm": term_data["termCode"],
        "courseSchedule": schedule,
        "courseCredits": num_credits,
        "courseSeatsTotal": seats_total,
        "courseSeatsFilled": seats_filled,
        "courseWaitlistLength": waitlist_length,
        "courseEnrollmentStatus": enrollment_status,
    }


def process_parallel(tasks, concurrency, end_time):
    """
    Run tasks in parallel. `tasks` is an iterator returning callables,
    which are invoked with no argments. `concurrency` specifies the
    maximum number of callables which may be invoked in parallel at
    the same time. `end_time` is a UNIX timestamp (see `time.time`)
    specifying the point at which further callables will not be
    executed.

    Any exceptions from the callables are caught and ignored. The
    return value is True if no exceptions were raised, and False
    otherwise.
    """
    lock = threading.Lock()
    num_done = 0
    error = False

    def target():
        nonlocal num_done, error
        if time.time() >= end_time:
            with lock:
                num_done += 1
            return
        with lock:
            try:
                task = next(tasks)
            except StopIteration:
                num_done += 1
                return
        try:
            task()
        except Exception:
            error = True
        if not error:
            thread = threading.Thread(target=target, daemon=True)
            thread.start()

    for _ in range(concurrency):
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    while True:
        time.sleep(0.1)
        if error or num_done >= concurrency:
            return not error


def main():
    """
    Read old course data from stdin and write new course data to
    stdout.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-crn", default=Unset)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--ignore-errors", action="store_true")
    args = parser.parse_args()
    start_time = time.time()
    old_data = json.load(sys.stdin)
    if old_data:
        # Get set of CRNs we have looked at already in this pass.
        completed = set(old_data["completed"])
        courses = old_data["courses"]
    else:
        # Start from scratch. No courses, no completed CRNs.
        completed = set()
        courses = {}
    srcdb, term_data = get_current_term()
    # Get set of CRNs and course codes that currently exist in the
    # database.
    available = get_available_courses(srcdb)
    # Remove already-parsed courses which no longer exist in the
    # database.
    courses = {crn: course for crn, course in courses.items()
               if crn in available}
    crns_left = set(available) - completed
    if not crns_left:
        completed = set()
        crns_left = set(available)

    def tasks():
        if not args.shuffle:
            crns = sorted(crns_left, key=lambda crn: available[crn])
        else:
            crns = list(crns_left)
            random.shuffle(crns)
        if args.start_crn is not Unset and args.start_crn in crns:
            crns = [crn for crn in crns if crn != args.start_crn]
            crns.insert(0, args.start_crn)
        lock = threading.Lock()
        for my_crn in crns:
            def task():
                nonlocal lock
                # Make a copy of the CRN so that we are not
                # referencing the loop iteration variable in this
                # callback (it will have since changed).
                crn = my_crn
                code = available[crn]
                print("Fetching data for (srcdb={}, crn={}, code={})"
                      .format(repr(srcdb), repr(crn), repr(code)),
                      file=sys.stderr)
                try:
                    cu_course = api_get_course(srcdb, crn, code)
                    course = convert_course(cu_course, term_data)
                except Exception:
                    with lock:
                        print(file=sys.stderr)
                        print("Error for (srcdb={}, crn={}, code={}):"
                              .format(repr(srcdb), repr(crn), repr(code)),
                              file=sys.stderr)
                        traceback.print_exc()
                    if not args.ignore_errors:
                        raise
                else:
                    courses[crn] = course
                    completed.add(crn)

            yield task

    # Start trying to finish up course data retrieval 15 seconds
    # before we will be timed out by the Hyperschedule worker.
    if not process_parallel(tasks(), concurrency=8, end_time=start_time + 45):
        sys.exit(1)

    data = {
        "terms": {
            term_data["termCode"]: term_data,
        },
        "courses": courses,
        "completed": sorted(completed, key=lambda crn: available[crn]),
    }
    json.dump(data, sys.stdout, indent=2)
    print()
