"""
Module for performing a webscrape of the HMC Portal. Main entry
point is get_latest_course_list.

This module uses two representations of courses, raw and canonical.
The raw version is taken more or less directly from the HTML on
Portal, and hasn't been validated yet. The canonical version is fully
validated and conforms to the API spec.

Just to avoid getting them confused, the raw representation uses
snake_case keys while the canonical representation uses camelCase
keys.
"""

import datetime
import os
import re

import bs4
import dateutil.parser
import psutil
import selenium.webdriver
import selenium.webdriver.chrome.options
import selenium.webdriver.support.ui

import libcourse

from util import ScrapeError, log

def unique_preserve_order(lst):
    """
    Deduplicate lst without changing the order. Return a new list.
    """
    new_lst = []
    for item in lst:
        if item not in new_lst:
            new_lst.append(item)
    return new_lst

def kill_existing_browser():
    """
    Kill any existing Google Chrome processes. This is necessary
    because Selenium is happy to start the browser, but it doesn't
    take care to clean it up if we kill Python -- thus resulting in
    multiple instances of Chrome, and way too much memory usage on
    Heroku.
    """
    for proc in psutil.process_iter():
        # We have to kill the helpers, too -- on Heroku we are using
        # Docker without baseimage-docker and thus zombie children
        # don't get reaped correctly; see
        # <https://blog.phusion.nl/2015/01/20/docker-and-the-pid-1-zombie-reaping-problem/>.
        if proc.name() in (
                "chromedriver", "Google Chrome", "Google Chrome Helper"):
            log("Killing {} process {}".format(repr(proc.name()), proc.pid))
            proc.kill()

def get_browser(headless):
    """
    Return a Selenium browser object, which can be either headless or
    not.
    """
    if headless:
        options = selenium.webdriver.chrome.options.Options()
        options.headless = True
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
        return selenium.webdriver.Chrome(options=options)
    return selenium.webdriver.Chrome()

def get_portal_html(browser):
    """
    Given a Selenium browser object, perform a webscrape of Portal and
    return the HTML of the course search results page as a string. May
    raise ScrapeError.
    """
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

def parse_table_row(row_idx, row):
    """
    Given a Selenium table row and the index, return a dictionary
    representing the raw course data for that row, or raise
    ScrapeError.
    """
    elements = row.find_all("td")
    try:
        (_add, course_code, name, faculty,
         seats, status, schedule, num_credits, begin, end) = elements
    except ValueError:
        raise ScrapeError(
            "could not extract course list table row elements "
            "from Portal HTML (for row {})".format(row_idx))
    return {
        "course_code": course_code.text,
        "course_name": name.text,
        "faculty": faculty.text,
        "seats": seats.text,
        "status": status.text,
        "schedule": [stime.text for stime in schedule.find_all("li")],
        "credits": num_credits.text,
        "begin_date": begin.text,
        "end_date": end.text,
    }

def parse_portal_html(html):
    """
    Given the Portal search results HTML as a string, return a list of
    raw course data dictionaries or raise ScrapeError.
    """
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
        raw_courses.append(parse_table_row(row_idx, row))

    return raw_courses

def format_raw_course(raw_course):
    """
    Given a raw course dictionary, return a string that can be output
    to the user in error messages.
    """
    # Try to put together a reasonable string representation of the
    # course for use in error messages, if it is malformed.
    desc = "{} {}".format(raw_course["course_code"], raw_course["course_name"])
    return re.sub(r"\s+", " ", desc).strip()

COURSE_REGEX = r"([A-Z]+) *?([0-9]+) *([A-Z]*[0-9]?) *([A-Z]{2})-([0-9]+)"
SCHEDULE_REGEX = (r"([MTWRFSU]+)\xa0([0-9]+:[0-9]+(?: ?[AP]M)?) - "
                  "([0-9]+:[0-9]+ ?[AP]M); ([A-Za-z0-9, ]+)")
DAYS_OF_WEEK = "MTWRFSU"

# pylint: disable = R0912, R0914, R0915
def process_course(raw_course):
    """
    Turn a raw course object into a canonical course object.
    """
    # noqa
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
            sorted(set(days), key=DAYS_OF_WEEK.index))
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
    schedule.sort(key=libcourse.schedule_sort_key)
    schedule = unique_preserve_order(schedule)
    quarter_credits = round(float(raw_course["credits"]) / 0.25)
    if quarter_credits < 0:
        raise ScrapeError(
            "negative credit count: {}".format(raw_course["credits"]))
    begin_date = dateutil.parser.parse(raw_course["begin_date"]).date()
    end_date = dateutil.parser.parse(raw_course["end_date"]).date()
    # First half-semester courses start (spring) January 1 through
    # January 31 or (fall) July 15 through September 15. (For some
    # reason, MATH 30B in Fall 2017 is listed as starting August 8.)
    first_half = (datetime.date(begin_date.year, 1, 1)
                  < begin_date
                  < datetime.date(begin_date.year, 1, 31)
                  or datetime.date(begin_date.year, 7, 15)
                  < begin_date
                  < datetime.date(begin_date.year, 9, 15))
    # Second half-semester courses for the spring end May 1 through
    # May 31, but there's also frosh chem pt.II which just *has* to be
    # different by ending 2/3 of the way through the semester. So we
    # also count that by allowing April 1 through April 30. Sigh. Fall
    # courses end December 1 through December 31.
    second_half = (datetime.date(end_date.year, 4, 1)
                   < end_date
                   < datetime.date(end_date.year, 5, 31)
                   or datetime.date(end_date.year, 12, 1)
                   < end_date
                   < datetime.date(end_date.year, 12, 31))
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

def get_latest_course_list(config):
    """
    Given a boolean indicating whether the Selenium browser should be
    headless, return a 2-tuple. The first element is a list of
    canonical course objects and the second element is a list of names
    of malformed courses. (You should not rely on the format of these
    names.)
    """
    if config["kill_chrome"]:
        kill_existing_browser()
    browser = get_browser(config["headless"])
    html = get_portal_html(browser)
    raw_courses = parse_portal_html(html)
    courses = []
    malformed_courses = []
    for raw_course in raw_courses:
        try:
            courses.append(process_course(raw_course))
        except ScrapeError:
            malformed_courses.append(format_raw_course(raw_course))
    courses.sort(key=libcourse.course_sort_key)
    return courses, malformed_courses
