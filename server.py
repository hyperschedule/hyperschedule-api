#!/usr/bin/env python3

import bs4
import datetime
import dateutil.parser
import http.server
import json
import natural.date
import os
import re
import selenium.webdriver
import selenium.webdriver.support.ui
import sys
import threading
import traceback

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

thread_lock = threading.Lock()
course_data = {}

## Course data retrieval

def get_browser(headless):
    if headless:
        # We can't use headless Chrome because of a bug in
        # ChromeDriver, see
        # https://bugs.chromium.org/p/chromedriver/issues/detail?id=2487.
        return selenium.webdriver.PhantomJS()
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

def schedule_sort_key(slot):
    return slot["days"], slot["startTime"], slot["endTime"]

def days_sort_key(day):
    return

def course_index_key(course):
    return (course["department"],
            course["courseNumber"],
            course["courseCodeSuffix"],
            course["school"],
            course["section"])

COURSE_REGEX = r"([A-Z]+) *?([0-9]+) *([A-Z]*[0-9]?) *([A-Z]{2})-([0-9]+)"
SCHEDULE_REGEX = (r"(?:([MTWRFSU]+)\xa0)?([0-9]+:[0-9]+(?: ?[AP]M)?) - "
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
    try:
        course_number = int(course_number)
    except ValueError:
        raise ScrapeError(
            "malformed course number: {}".format(repr(course_number)))
    if course_number <= 0:
        raise ScrapeError(
            "non-positive course number: {}".format(course_number))
    if not school:
        raise ScrapeError("empty string for school")
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
    for raw_course in raw_courses:
        try:
            courses.append(process_course(raw_course))
        except ScrapeError as e:
            raise (ScrapeError("could not process course {}: {}"
                               .format(repr(raw_course["course_code"]), e))
                   .with_traceback(sys.exc_info()[2]))
    courses.sort(key=course_index_key)
    return courses

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
        key = course_index_key(course)
        if key in course_index:
            raise ScrapeError("more than one course matching {}"
                              .format(repr(format_course_code(course))))
        course_index[key] = course
    return course_index

def update_course_data(timestamp, courses):
    global course_data
    with thread_lock:
        course_data = {
            "courses": courses,
            "last_update": timestamp,
        }

def fetch_and_update_course_data(browser):
    timestamp = datetime.datetime.now()
    courses = get_latest_course_list(browser)
    index_courses(courses)
    update_course_data(timestamp, courses)

def run_fetch_task(browser, backoff_factor, base_delay, delay=None):
    delay = delay or base_delay
    try:
        log("Starting course data update...")
        fetch_and_update_course_data(browser)
    except Exception:
        log("Failed to update course data:\n"
            + traceback.format_exc().rstrip())
        delay *= backoff_factor
        log("Trying again after {:.0f} seconds.".format(delay))
    else:
        log("Finished course data update.")
        delay = base_delay
        log("Updating again after {:.0f} seconds.".format(delay))
    t = threading.Timer(
        delay, lambda: run_fetch_task(
            browser, backoff_factor, base_delay, delay))
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

class HTTPHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            with open("index.html", "rb") as f:
                html = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(html)
        elif self.path.rstrip("/") == "/api/v1/all-courses":
            with thread_lock:
                if "courses" in course_data:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    courses = course_data["courses"]
                    timestamp = course_data["last_update"]
                    now = datetime.datetime.now()
                    last_updated = natural.date.delta(
                        timestamp, now,
                        # For compatibility with the old API server
                        # which used moment.js.
                        justnow=datetime.timedelta(seconds=45))[0]
                    if last_updated != "just now":
                        last_updated += " ago"
                    response = json.dumps({
                        "courses": courses,
                        "lastUpdate": last_updated,
                    })
                    self.wfile.write(response.encode())
                else:
                    self.send_error(503, explain=("The course data is not yet "
                                                  "available. Please wait"))
        else:
            self.send_error(404)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        http.server.BaseHTTPRequestHandler.end_headers(self)

    def log_message(self, format, *args):
        log(format % args)

    def log_request(self, code="-", size="-"):
        self.log_message("{} : {} {}".format(code, self.command, self.path))

    error_message_format = ERROR_MESSAGE_FORMAT

def run_server(port):
    httpd = http.server.HTTPServer(("", port), HTTPHandler)
    log("Starting server on port {}...".format(port))
    httpd.serve_forever()

if __name__ == "__main__":
    port = os.environ.get("PORT", "3000")
    try:
        port = int(port)
    except ValueError:
        die("malformed PORT: {}".format(repr(port)))
    production = None
    headless = None
    for arg in sys.argv[1:]:
        if arg in ("--dev", "--develop", "--development"):
            production = False
        elif arg in ("--prod", "--production"):
            production = True
        elif arg in ("--headless"):
            headless = True
        elif arg in ("--no-headless"):
            headless = False
        else:
            die("unexpected argument: {}".format(repr(arg)))
    if production is None:
        die("you must specify either --dev or --prod")
    if headless is None:
        headless = True
    browser = get_browser(headless)
    backoff_factor = 1.5 if production else 1.0
    base_delay = 5
    t = threading.Thread(
        target=lambda: run_fetch_task(
            browser, backoff_factor, base_delay), daemon=True)
    t.start()
    run_server(port)

# Local Variables:
# outline-regexp: "^##+"
# End:
