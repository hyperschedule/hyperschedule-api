#!/usr/bin/env python3

import bs4
import copy
import datetime
import dateutil.parser
import http
import http.server
import itertools
import json
import json.decoder
import multiprocessing
import natural.date
import os
import queue
import re
import selenium.webdriver
import selenium.webdriver.chrome.options
import selenium.webdriver.support.ui
import sys
import threading
import traceback

## Utilities

def unique(lst):
    new_lst = []
    for item in lst :
        if item not in new_lst :
            new_lst += [item]
    return new_lst

## Exceptions

class ScrapeError(Exception):
    pass

## Logging

def log(message):
    print("[{}] {}".format(
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        message), file=sys.stderr)

def die(message):
    log("fatal: " + message)
    sys.exit(1)

## Thread-global variables

INITIAL_COURSE_DATA = {
    "current": None,
    "index": None,
    "initial_timestamp": None,
    "updates": [],
    "timestamp": None,
}

thread_lock = threading.Lock()
course_data = copy.deepcopy(INITIAL_COURSE_DATA)

## Course data retrieval

def get_browser(headless):
    if headless:
        options = selenium.webdriver.chrome.options.Options()
        options.set_headless(True)
        # Disabling scroll bars is important, see
        # https://bugs.chromium.org/p/chromedriver/issues/detail?id=2487.
        options.add_argument("--hide-scrollbars")
        # The Chrome binary is at a nonstandard location on Heroku,
        # see [1].
        #
        # [1]: https://github.com/heroku/heroku-buildpack-google-chrome.
        binary = os.environ.get("GOOGLE_CHROME_SHIM")
        if binary:
            options.binary_location = binary
        return selenium.webdriver.Chrome(chrome_options=options)
    else:
        return selenium.webdriver.Chrome()

def get_portal_html(browser):
    url = ("https://portal.hmc.edu/ICS/Portal_Homepage.jnz?"
           "portlet=Course_Schedules&screen=Advanced+Course+Search"
           "&screenType=next")
    browser.get(url)

    term_dropdown = selenium.webdriver.support.ui.Select(
        browser.find_element_by_id("pg0_V_ddlTerm"))
    term_names = [option.text for option in term_dropdown.options]

    terms = []
    for term_name in term_names:
        match = re.match(r"\s*(FA|SP)\s*([0-9]{4})\s*", term_name)
        if match:
            fall_or_spring, year_str = match.groups()
            terms.append((int(year_str), fall_or_spring == "FA", term_name))

    if not terms:
        raise ScrapeError(
            "couldn't parse any term names (from: {})"
            .format(repr(term_names)))

    most_recent_term = max(terms)
    term_dropdown.select_by_visible_text(most_recent_term[2])

    title_input = browser.find_element_by_id("pg0_V_txtTitleRestrictor")
    title_input.clear()
    title_input.send_keys("*")

    search_button = browser.find_element_by_id("pg0_V_btnSearch")
    search_button.click()

    show_all_checkbox = browser.find_element_by_id("pg0_V_lnkShowAll")
    show_all_checkbox.click()

    return browser.page_source

def parse_portal_html(html):
    soup = bs4.BeautifulSoup(html, "lxml")

    table = soup.find(id="pg0_V_dgCourses")
    if not table:
        raise ScrapeError("could not find course list table in Portal HTML")

    table_body = table.find("tbody")
    if not table_body:
        raise ScrapeError(
            "could not find course list table body in Portal HTML")

    table_rows = table_body.find_all("tr", recursive=False)
    if not table_rows:
        raise ScrapeError(
            "could not extract course list table rows from Portal HTML")

    raw_courses = []
    for row_idx, row in enumerate(table_rows):
        if "style" in row.attrs and row.attrs["style"] == "display:none;":
            continue
        elements = row.find_all("td")
        try:
            (add, course_code, name, faculty,
             seats, status, schedule, num_credits, begin, end) = elements
        except ValueError:
            raise ScrapeError(
                "could not extract course list table row elements "
                "from Portal HTML (for row {})".format(row_idx))
        raw_courses.append({
            "course_code": course_code.text,
            "course_name": name.text,
            "faculty": faculty.text,
            "seats": seats.text,
            "status": status.text,
            "schedule": [stime.text for stime in schedule.find_all("li")],
            "credits": num_credits.text,
            "begin_date": begin.text,
            "end_date": end.text,
        })

    return raw_courses

def format_raw_course(raw_course):
    # Try to put together a reasonable string representation of the
    # course for use in error messages, if it is malformed.
    desc = "{} {}".format(raw_course["course_code"], raw_course["course_name"])
    return re.sub(r"\s+", " ", desc).strip()

def schedule_sort_key(slot):
    return slot["days"], slot["startTime"], slot["endTime"]

def days_sort_key(day):
    return

COURSE_ATTRS = [
    "courseCodeSuffix",
    "courseName",
    "courseNumber",
    "courseStatus",
    "department",
    "endDate",
    "faculty",
    "firstHalfSemester",
    "openSeats",
    "quarterCredits",
    "schedule",
    "school",
    "secondHalfSemester",
    "section",
    "startDate",
    "totalSeats",
]

COURSE_INDEX_ATTRS = (
    "department",
    "courseNumber",
    "courseCodeSuffix",
    "school",
    "section",
)

COURSE_INDEX_ATTRS_CONVERT_TO_INT = {
    "department": False,
    "courseNumber": True,
    "courseCodeSuffix": False,
    "school": False,
    "section": True,
}

assert set(COURSE_INDEX_ATTRS) == set(COURSE_INDEX_ATTRS_CONVERT_TO_INT)

def course_to_index_key(course):
    return "/".join(str(course[attr]) for attr in COURSE_INDEX_ATTRS)

def course_from_index_key(key):
    course = {}
    for attr, value in zip(COURSE_INDEX_ATTRS, key.split("/")):
        if COURSE_INDEX_ATTRS_CONVERT_TO_INT[attr]:
            value = int(value)
        course[attr] = value
    return course

def course_sort_key(course):
    return tuple(course[attr] for attr in COURSE_INDEX_ATTRS)

COURSE_REGEX = r"([A-Z]+) *?([0-9]+) *([A-Z]*[0-9]?) *([A-Z]{2})-([0-9]+)"
SCHEDULE_REGEX = (r"([MTWRFSU]+)\xa0([0-9]+:[0-9]+(?: ?[AP]M)?) - "
                  "([0-9]+:[0-9]+ ?[AP]M); ([A-Za-z0-9, ]+)")
DAYS_OF_WEEK = "MTWRFSU"

def process_course(raw_course):
    course_code = raw_course["course_code"].strip()
    match = re.match(COURSE_REGEX, course_code)
    if not match:
        raise ScrapeError(
            "malformed course code: {}".format(repr(course_code)))
    department, course_number, num_suffix, school, section = match.groups()
    if not department:
        raise ScrapeError("empty string for department")
    if "/" in department:
        raise ScrapeError("department contains slashes: {}"
                          .format(repr(department)))
    try:
        course_number = int(course_number)
    except ValueError:
        raise ScrapeError(
            "malformed course number: {}".format(repr(course_number)))
    if course_number <= 0:
        raise ScrapeError(
            "non-positive course number: {}".format(course_number))
    if "/" in num_suffix:
        raise ScrapeError("course code suffix contains slashes: {}"
                          .format(repr(num_suffix)))
    if not school:
        raise ScrapeError("empty string for school")
    if "/" in school:
        raise ScrapeError("school contains slashes: {}".format(repr(school)))
    try:
        section = int(section)
    except ValueError:
        raise ScrapeError(
            "malformed section number: {}".format(repr(section)))
    if section <= 0:
        raise ScrapeError("non-positive section number: {}".format(section))
    course_name = raw_course["course_name"].strip()
    if not course_name:
        raise ScrapeError("empty string for course name")
    faculty = sorted(set(re.split(r"\s*\n\s*", raw_course["faculty"].strip())))
    if not faculty:
        raise ScrapeError("no faculty")
    for faculty_name in faculty:
        if not faculty_name:
            raise ScrapeError("faculty with empty name")
    match = re.match(r"([0-9]+)/([0-9]+)", raw_course["seats"])
    if not match:
        raise ScrapeError(
            "malformed seat count: {}".format(repr(raw_course["seats"])))
    open_seats, total_seats = map(int, match.groups())
    if open_seats < 0:
        raise ScrapeError("negative open seat count: {}".format(open_seats))
    if total_seats < 0:
        raise ScrapeError("negative total seat count: {}".format(total_seats))
    course_status = raw_course["status"].lower()
    if course_status not in ("open", "closed", "reopened"):
        raise ScrapeError(
            "unknown course status: {}".format(repr(course_status)))
    schedule = []
    for slot in raw_course["schedule"]:
        if slot.startswith("0:00 - 0:00 AM"):
            continue
        match = re.match(SCHEDULE_REGEX, slot)
        if not match:
            raise ScrapeError("malformed schedule slot: {}".format(repr(slot)))
        days, start, end, location = match.groups()
        for day in days:
            if day not in DAYS_OF_WEEK:
                raise ScrapeError("unknown day of week {} in schedule slot {}"
                                  .format(repr(day), repr(slot)))
        days = "".join(
            sorted(set(days), key=lambda day: DAYS_OF_WEEK.index(day)))
        if not days:
            raise ScrapeError("no days in schedule slot {}".format(repr(slot)))
        if not (start.endswith("AM") or start.endswith("PM")):
            start += end[-2:]
        try:
            start = dateutil.parser.parse(start).time()
        except ValueError:
            raise ScrapeError("malformed start time {} in schedule slot {}"
                              .format(repr(start), repr(slot)))
        try:
            end = dateutil.parser.parse(end).time()
        except ValueError:
            raise ScrapeError("malformed end time {} in schedule slot {}"
                              .format(repr(end), repr(slot)))
        location = " ".join(location.strip().split())
        if not location:
            raise ScrapeError("empty string for location")
        # Start using camelCase here because we are constructing
        # objects that will be returned from the API as JSON, and our
        # API is camelCase.
        schedule.append({
            "days": days,
            "location": location,
            "startTime": start.strftime("%H:%M"),
            "endTime": end.strftime("%H:%M"),
        })
    schedule.sort(key=schedule_sort_key)
    schedule = unique(schedule)
    quarter_credits = round(float(raw_course["credits"]) / 0.25)
    if quarter_credits < 0:
        raise ScrapeError(
            "negative credit count: {}".format(raw_course["credits"]))
    begin_date = dateutil.parser.parse(raw_course["begin_date"]).date()
    end_date = dateutil.parser.parse(raw_course["end_date"]).date()
    # First half-semester courses start (spring) January 1 through
    # January 31 or (fall) July 15 through September 15. (For some
    # reason, MATH 30B in Fall 2017 is listed as starting August 8.)
    first_half = (datetime.date(begin_date.year, 1, 1) <
                  begin_date <
                  datetime.date(begin_date.year, 1, 31)
                  or
                  datetime.date(begin_date.year, 7, 15) <
                  begin_date <
                  datetime.date(begin_date.year, 9, 15))
    # Second half-semester courses for the spring end May 1 through
    # May 31, but there's also frosh chem pt.II which just *has* to be
    # different by ending 2/3 of the way through the semester. So we
    # also count that by allowing April 1 through April 30. Sigh. Fall
    # courses end December 1 through December 31.
    second_half = (datetime.date(end_date.year, 4, 1) <
                   end_date <
                   datetime.date(end_date.year, 5, 31)
                   or
                   datetime.date(end_date.year, 12, 1) <
                   end_date <
                   datetime.date(end_date.year, 12, 31))
    if not (first_half or second_half):
        raise ScrapeError("weird date range {}-{}"
                          .format(begin_date.strftime("%Y-%m-%d"),
                                  end_date.strftime("%Y-%m-%d")))
    return {
        "department": department,
        "courseNumber": course_number,
        "courseCodeSuffix": num_suffix,
        "school": school,
        "section": section,
        "courseName": course_name,
        "faculty": faculty,
        "openSeats": open_seats,
        "totalSeats": total_seats,
        "courseStatus": course_status,
        "schedule": schedule,
        "quarterCredits": quarter_credits,
        "firstHalfSemester": first_half,
        "secondHalfSemester": second_half,
        "startDate": begin_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
    }

def get_latest_course_list(browser):
    html = get_portal_html(browser)
    raw_courses = parse_portal_html(html)
    courses = []
    malformed_courses = []
    for raw_course in raw_courses:
        try:
            courses.append(process_course(raw_course))
        except ScrapeError as e:
            malformed_courses.append(format_raw_course(raw_course))
    courses.sort(key=course_sort_key)
    return courses, malformed_courses

# This should probably only be using attributes in COURSE_INDEX_ATTRS,
# so that any two non-distinct courses (see the API documentation)
# have the same formatted course code.
def format_course_code(course):
    return "{} {:03d}{} {}-{:02d}".format(
        course["department"],
        course["courseNumber"],
        course["courseCodeSuffix"],
        course["school"],
        course["section"])

def index_courses(courses):
    course_index = {}
    for course in courses:
        key = course_to_index_key(course)
        if key in course_index:
            raise ScrapeError("more than one course matching {}"
                              .format(repr(format_course_code(course))))
        course_index[key] = course
    return course_index

def compute_update(old_courses_index, new_courses_index):
    old_courses_keys = set(old_courses_index)
    new_courses_keys = set(new_courses_index)
    maybe_modified_keys = new_courses_keys & old_courses_keys
    modified_keys_and_attrs = {}
    for key in maybe_modified_keys:
        old_course = old_courses_index[key]
        new_course = new_courses_index[key]
        attrs = []
        for attr in COURSE_ATTRS:
            if old_course[attr] != new_course[attr]:
                attrs.append(attr)
        if attrs:
            modified_keys_and_attrs[key] = attrs
    return {
        "added": list(new_courses_keys - old_courses_keys),
        "removed": list(old_courses_keys - new_courses_keys),
        "modified": modified_keys_and_attrs,
    }

def compute_diff(since):
    added = set()
    removed = set()
    modified = {}
    for timestamp, update in course_data["updates"]:
        if timestamp > since:
            for key, attrs in update["modified"].items():
                assert key not in removed
                if key not in modified:
                    modified[key] = set()
                modified[key] |= set(attrs)
            for key in update["added"]:
                assert key not in modified and key not in added
                if key in removed:
                    removed.remove(key)
                    modified[key] = set(COURSE_ATTRS)
                else:
                    added.add(key)
            for key in update["removed"]:
                assert key not in removed
                if key in modified:
                    del modified[key]
                if key in added:
                    added.remove(key)
                else:
                    removed.add(key)
    index = course_data["index"]
    added_courses = []
    for key in added:
        added_courses.append(index[key])
    removed_courses = []
    for key in removed:
        removed_courses.append(course_from_index_key(key))
    modified_courses = []
    for key in modified:
        current_course = index[key]
        course = {}
        attrs = modified[key]
        for attr in itertools.chain(COURSE_INDEX_ATTRS, attrs):
            course[attr] = current_course[attr]
        modified_courses.append(course)
    return {
        "added": added_courses,
        "removed": removed_courses,
        "modified": modified_courses,
    }

MAX_UPDATES_SAVED = 100

def update_course_data(timestamp, courses, index, malformed_courses):
    global course_data
    with thread_lock:
        last_index = course_data["index"]
        if last_index is not None:
            updates = course_data["updates"]
            # Use a list so we can serialize to JSON.
            updates.append([timestamp, compute_update(last_index, index)])
            if len(updates) > MAX_UPDATES_SAVED:
                updates[:] = updates[len(updates) - MAX_UPDATES_SAVED:]
        else:
            course_data["initial_timestamp"] = timestamp
        course_data["current"] = courses
        course_data["index"] = index
        course_data["timestamp"] = timestamp
        course_data["malformed"] = malformed_courses

def fetch_and_update_course_data(browser):
    timestamp = int(datetime.datetime.now().timestamp())
    process_queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=lambda: process_queue.put(get_latest_course_list(browser)))
    process.start()
    try:
        # Usually the course data update takes about 20 seconds.
        # Giving it 60 seconds should be more than enough.
        courses, malformed_courses = process_queue.get(timeout=60)
    except queue.Empty:
        process.terminate()
        raise ScrapeError("timed out")
    finally:
        process.join()
    update_course_data(
        timestamp, courses, index_courses(courses), malformed_courses)

def write_course_data_to_cache_file():
    log("Writing course data to cache on disk...")
    with open(COURSE_DATA_CACHE_FILE, "w") as f:
        json.dump(course_data, f)
    log("Finished writing course data to disk.")

COURSE_DATA_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "course-data.json")

def run_single_fetch_task(browser, use_cache):
    try:
        log("Starting course data update...")
        fetch_and_update_course_data(browser)
        if use_cache:
            write_course_data_to_cache_file()
    except Exception:
        log("Failed to update course data:\n"
            + traceback.format_exc().rstrip())
        return False
    else:
        log("Finished course data update.")
        return True

def run_fetch_task(browser, backoff_factor, base_delay, use_cache, delay=None):
    delay = delay or base_delay
    if run_single_fetch_task(browser, use_cache):
        delay = base_delay
        log("Updating again after {:.0f} seconds.".format(delay))
    else:
        delay *= backoff_factor
        log("Trying again after {:.0f} seconds.".format(delay))
    t = threading.Timer(
        delay, lambda: run_fetch_task(
            browser, backoff_factor, base_delay, use_cache, delay))
    t.start()

## Server

ERROR_MESSAGE_FORMAT = """\
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
  </head>
  <body>
    <h1>%(code)d %(message)s</h1>
    <p>%(explain)s.</p>
  </body>
</html>
"""

class HTTPServer(http.server.ThreadingHTTPServer):

    def __init__(self, attrs, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, value in attrs.items():
            setattr(self, key, value)

class HTTPHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            with open("index.html", "rb") as f:
                html = f.read()
                self.send_response(http.HTTPStatus.OK)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(html)
            return
        match = re.match(r"/api/v([12])/all-courses/?", self.path)
        if match:
            with thread_lock:
                if course_data["current"]:
                    courses = course_data["current"]
                    timestamp = course_data["timestamp"]
                    if match.group(1) == "1":
                        # Paranoid backwards compatibility for the
                        # output format of the old API.
                        now = int(datetime.datetime.now().timestamp())
                        last_updated = natural.date.delta(
                            timestamp, now,
                            justnow=datetime.timedelta(seconds=45))[0]
                        if last_updated != "just now":
                            last_updated += " ago"
                        response = {
                            "courses": courses,
                            "lastUpdate": last_updated,
                        }
                    else:
                        response = {
                            "courses": courses,
                            "timestamp": timestamp,
                            "malformedCourseCount":
                            len(course_data["malformed"]),
                        }
                    response_body = json.dumps(response).encode()
                    self.send_response(http.HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(response_body)
                else:
                    self.send_error(http.HTTPStatus.SERVICE_UNAVAILABLE,
                                    explain=("The course data is not yet "
                                             "available. Please wait"))
            return
        match = re.match(r"/api/v2/courses-since/([-0-9]+)/?", self.path)
        if match:
            with thread_lock:
                try:
                    since = int(match.group(1))
                except ValueError:
                    self.send_error(
                        http.HTTPStatus.BAD_REQUEST,
                        explain=("Malformed timestamp {}"
                                 .format(repr(match.group(1)))))
                    return
                timestamp = course_data["timestamp"]
                if ((course_data["current"] and
                     since >= course_data["initial_timestamp"])):
                    diff = compute_diff(since)
                    response = {
                        "incremental": True,
                        "diff": diff,
                        "timestamp": timestamp,
                        "malformedCourseCount":
                        len(course_data["malformed"]),
                    }
                elif course_data["current"]:
                    response = {
                        "incremental": False,
                        "courses": course_data["current"],
                        "timestamp": timestamp,
                        "malformedCourseCount":
                        len(course_data["malformed"]),
                    }
                else:
                    self.send_error(http.HTTPStatus.SERVICE_UNAVAILABLE,
                                    explain=("The course data is not yet "
                                             "available. Please wait"))
                    return
                response_body = json.dumps(response).encode()
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response_body)
            return
        match = re.match(r"/api/v2/malformed-courses/?", self.path)
        if match:
            with thread_lock:
                response_body = json.dumps(course_data["malformed"]).encode()
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response_body)
            return
        match = re.match(r"/experimental/course-data/?", self.path)
        if match:
            with thread_lock:
                response_body = json.dumps(course_data).encode()
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response_body)
            return
        self.send_error(http.HTTPStatus.NOT_FOUND)
        return

    def do_PUT(self):
        global course_data
        if not self.server.debug:
            self.send_error(http.HTTPStatus.NOT_IMPLEMENTED,
                            message="Unsupported method ('PUT')")
            return
        match = re.match(r"/debug/set-courses(?:/([-0-9]+))?/?", self.path)
        if match:
            timestamp = int(match.group(1) or
                            datetime.datetime.now().timestamp())
            content_length = int(
                self.headers.get("Content-Length", 0))
            courses = json.loads(self.rfile.read(content_length).decode())
            index = index_courses(courses)
            update_course_data(timestamp, courses, index)
            if self.server.use_cache:
                write_course_data_to_cache_file()
            self.send_response(http.HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if self.path.rstrip("/") == "/debug/scrape":
            t = threading.Thread(
                target=lambda: run_single_fetch_task(
                    self.server.browser,
                    self.server.use_cache))
            t.start()
            self.send_response(http.HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if self.path.rstrip("/") == "/debug/reset":
            with thread_lock:
                course_data = INITIAL_COURSE_DATA
                if self.server.use_cache:
                    write_course_data_to_cache_file()
            self.send_response(http.HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self.send_error(http.HTTPStatus.NOT_FOUND)
        return

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        http.server.BaseHTTPRequestHandler.end_headers(self)

    def log_message(self, format, *args):
        log(format % args)

    def log_request(self, code="-", size="-"):
        self.log_message("{} : {} {}".format(code, self.command, self.path))

    error_message_format = ERROR_MESSAGE_FORMAT

if __name__ == "__main__":
    port = os.environ.get("PORT", "3000")
    try:
        port = int(port)
    except ValueError:
        die("malformed PORT: {}".format(repr(port)))
    production = None
    headless = None
    use_cache = None
    use_scraper = None
    for arg in sys.argv[1:]:
        if arg in ("--dev", "--develop", "--development"):
            production = False
        elif arg in ("--prod", "--production"):
            production = True
        elif arg in ("--headless"):
            headless = True
        elif arg in ("--no-headless"):
            headless = False
        elif arg in ("--cache"):
            use_cache = True
        elif arg in ("--no-cache"):
            use_cache = False
        elif arg in ("--scrape"):
            use_scraper = True
        elif arg in ("--no-scrape"):
            use_scraper = False
        else:
            die("unexpected argument: {}".format(repr(arg)))
    if production is None:
        die("you must specify either --dev or --prod")
    if headless is None:
        headless = True
    if use_cache is None:
        use_cache = not production
    if use_scraper is None:
        use_scraper = True
    browser = get_browser(headless)
    if use_cache:
        try:
            with open(COURSE_DATA_CACHE_FILE) as f:
                log("Loading cached course data from disk...")
                course_data = json.load(f)
                log("Finished loading cached course data.")
        except FileNotFoundError:
            pass
        except json.decoder.JSONDecodeError:
            log("Failed to load cached course data due to JSON parse error.")
    if use_scraper:
        backoff_factor = 1.5 if production else 1.0
        base_delay = 5
        t = threading.Thread(
            target=lambda: run_fetch_task(
                browser, backoff_factor, base_delay, use_cache), daemon=True)
        t.start()
    httpd = HTTPServer({
        "debug": not production,
        "browser": browser,
        "use_cache": use_cache,
    }, ("", port), HTTPHandler)
    log("Starting server on port {}...".format(port))
    httpd.serve_forever()

# Local Variables:
# outline-regexp: "^##+"
# End:
