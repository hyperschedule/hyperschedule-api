"""
Module for retrieving data from the HMC Portal and formatting it
appropriately for the frontend (sans course descriptions).

Main entry point is `get_courses`.

This module returns course objects as described in the Hyperschedule
API spec, but also uses an intermediate ("raw") representation for
course data that has been extracted from Portal but not yet validated.
To avoid confusion, the intermediate representation uses snake_case
rather than camelCase keys.
"""

import collections
import datetime
import os
import re
import string

import bs4
import dateutil.parser
import frozendict
import selenium.webdriver
import selenium.webdriver.chrome.options
import selenium.webdriver.support.ui

import hyperschedule.scraper as scraper
import hyperschedule.scraper.shared as shared
import hyperschedule.util as util

from hyperschedule.util import ScrapeError

def unique_preserve_order(lst):
    """
    Deduplicate lst without changing the order. Return a new list.

    The elements of lst are not required to be hashable.
    """
    new_lst = []
    for item in lst:
        if item not in new_lst:
            new_lst.append(item)
    return new_lst

def get_browser():
    """
    Return a Selenium browser object. Whether it is headless is
    controlled by the 'headless' config var.
    """
    if util.get_env_boolean("headless"):
        options = selenium.webdriver.chrome.options.Options()
        options.headless = True
        # Disabling scroll bars is important, see
        # <https://bugs.chromium.org/p/chromedriver/issues/detail?id=2487>.
        options.add_argument("--hide-scrollbars")
        # The Chrome binary is at a nonstandard location on Heroku,
        # see <https://github.com/heroku/heroku-buildpack-google-chrome>.
        binary = os.environ.get("GOOGLE_CHROME_SHIM")
        if binary:
            options.binary_location = binary
        return selenium.webdriver.Chrome(options=options)
    return selenium.webdriver.Chrome()

def get_portal_html(browser):
    """
    Given a Selenium browser object, perform a webscrape of Portal.
    Return a tuple (html, term) with the HTML of the course search
    results page as a string and the current term (for which courses
    were retrieved) also as a string.

    Raise ScrapeError if something goes wrong with the browser or
    Portal.
    """
    util.log_verbose("Scraping Portal")
    url = ("https://portal.hmc.edu/ICS/Portal_Homepage.jnz?"
           "portlet=Course_Schedules&screen=Advanced+Course+Search"
           "&screenType=next")
    browser.get(url)

    term_dropdown = selenium.webdriver.support.ui.Select(
        browser.find_element_by_id("pg0_V_ddlTerm"))
    term_names = [option.text for option in term_dropdown.options]

    terms_info = []
    for term_name in term_names:
        match = re.match(r"\s*(FA|SP)\s*([0-9]{4})\s*", term_name)
        if match:
            fall_or_spring, year_str = match.groups()
            terms_info.append(
                (int(year_str), fall_or_spring == "FA", term_name))

    if not terms_info:
        raise ScrapeError(
            "couldn't parse any term names (from: {})"
            .format(repr(term_names)))

    term_info = max(terms_info)
    term = term_info[2]
    term_dropdown.select_by_visible_text(term)

    title_input = browser.find_element_by_id("pg0_V_txtTitleRestrictor")
    title_input.clear()
    title_input.send_keys("*")

    search_button = browser.find_element_by_id("pg0_V_btnSearch")
    search_button.click()

    show_all_checkbox = browser.find_element_by_id("pg0_V_lnkShowAll")
    show_all_checkbox.click()

    return browser.page_source, " ".join(term.split())

def parse_table_row(row_idx, row):
    """
    Given a Selenium table row and the index, return a dictionary
    representing the raw course data for that row.

    Raise ScrapeError if the HTML does not have the desired data.
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
    raw course data dictionaries.

    If HTML is bad, raise ScrapeError.
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

COURSE_AND_SECTION_REGEX = r"([^-]+)-([0-9]+)"
SCHEDULE_REGEX = (r"([MTWRFSU]+)\xa0([0-9]+:[0-9]+(?: ?[AP]M)?) - "
                  "([0-9]+:[0-9]+ ?[AP]M); ([A-Za-z0-9, ]+)")
DAYS_OF_WEEK = "MTWRFSU"

def process_course(raw_course, term):
    """
    Turn a raw course object into something that the frontend can use.
    Return a dictionary.

    If the raw course object has invalid data, raise ScrapeError.
    """
    course_code = raw_course["course_code"].strip()
    course_info = shared.parse_course_code(course_code, with_section=True)
    course_code = shared.course_info_as_string(course_info)
    sort_key = shared.course_info_as_list(course_info, with_section=True)
    mutual_exclusion_key = shared.course_info_as_list(
        course_info, with_section=False)
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
    filled_seats, total_seats = map(int, match.groups())
    if filled_seats < 0:
        raise ScrapeError(
            "negative filled seat count: {}".format(filled_seats))
    if total_seats < 0:
        raise ScrapeError("negative total seat count: {}".format(total_seats))
    course_status = raw_course["status"].lower()
    if course_status not in ("open", "closed", "reopened"):
        raise ScrapeError(
            "unknown course status: {}".format(repr(course_status)))
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
    if first_half and second_half:
        term_count = 1
        terms = [0]
    elif first_half and not second_half:
        term_count = 2
        terms = [0]
    elif second_half and not first_half:
        term_count = 2
        terms = [1]
    else:
        raise ScrapeError("weird date range {}-{}"
                          .format(begin_date.strftime("%Y-%m-%d"),
                                  end_date.strftime("%Y-%m-%d")))
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
        # objects that will be returned from the API as JSON -- no
        # longer just intermediate objects private to this module.
        schedule.append({
            "scheduleDays": days,
            "scheduleStartTime": start.strftime("%H:%M"),
            "scheduleEndTime": end.strftime("%H:%M"),
            "scheduleStartDate": begin_date.strftime("%Y-%m-%d"),
            "scheduleEndDate": end_date.strftime("%Y-%m-%d"),
            "scheduleTermCount": term_count,
            "scheduleTerms": terms,
            "scheduleLocation": location,
        })
    schedule = unique_preserve_order(schedule)
    num_credits = raw_course["credits"]
    try:
        num_credits = float(num_credits)
    except ValueError:
        raise ScrapeError(
            "malformed credit count: {}".format(repr(num_credits)))
    if num_credits < 0:
        raise ScrapeError(
            "negative credit count: {}".format(raw_course["credits"]))
    if "Colloquium" in course_name and num_credits == 0:
        num_credits = 0.5
    elif re.match("PE ", course_code) and num_credits == 0:
        num_credits = 1
    elif num_credits == 0.25:
        num_credits = 1
    elif not re.search(r"HM-", course_code):
        num_credits *= 3
    num_credits = str(num_credits)
    course_description = raw_course["course_description"]
    return {
        "courseCode": course_code,
        "courseName": course_name,
        "courseSortKey": sort_key,
        "courseMutualExclusionKey": mutual_exclusion_key,
        "courseDescription": course_description,
        "courseInstructors": faculty,
        "courseTerm": term,
        "courseSchedule": schedule,
        "courseCredits": num_credits,
        "courseSeatsTotal": total_seats,
        "courseSeatsFilled": filled_seats,
        "courseWaitlistLength": None,
        "courseEnrollmentStatus": course_status,
    }

def get_courses(desc_index):
    """
    Return a tuple containing the list of course objects and the
    current term. Takes `desc_index` as returned by
    `lingk.get_course_descriptions`.
    """
    browser = get_browser()
    html, term = get_portal_html(browser)
    # Save on memory.
    scraper.kill_google_chrome()
    # Count how many courses we add descriptions to, so we can fail if
    # there aren't enough.
    num_descs_added = 0
    # Count how many courses we fail to parse, so we can fail if there
    # are too many.
    num_failed = 0
    # Get the first round of raw courses from Portal.
    raw_courses_1 = parse_portal_html(html)
    # Add course descriptions to them, using the raw course codes.
    # Also collect the course codes into a dictionary so that we can
    # deduplicate them.
    raw_courses_2 = []
    course_info_map = collections.defaultdict(list)
    for raw_course in raw_courses_1:
        try:
            course_code = raw_course["course_code"].strip()
            course_info = shared.parse_course_code(
                course_code, with_section=True)
            desc_key = tuple(
                shared.course_info_as_list(course_info, with_section=False))
            desc = desc_index.get(desc_key)
            if desc:
                num_descs_added += 1
            raw_course["course_description"] = desc
            course_info_map[frozendict.frozendict(course_info)].append(
                raw_course)
        except ScrapeError:
            util.log_verbose(
                "Failed to parse course: {}"
                .format(repr(format_raw_course(raw_course))))
            num_failed += 1
            continue
        raw_courses_2.append(raw_course)
    if num_descs_added < 100:
        raise ScrapeError("not enough course descriptions added: {}"
                          .format(num_descs_added))
    # Deduplicate course codes.
    raw_courses_3 = []
    for course_info, courses in course_info_map.items():
        if len(courses) > 1:
            if course_info["course_code_suffix"]:
                util.log_verbose(
                    "Duplicate course with suffix ({} copies): {}"
                    .format(len(courses), repr(format_raw_course(courses[0]))))
                num_failed += len(courses)
                continue
            if len(courses) > len(string.ascii_uppercase):
                util.log_verbose(
                    "Duplicate course with too many copies ({}): {}"
                    .format(len(courses), repr(format_raw_course(courses[0]))))
                num_failed += len(courses)
                continue
            for course, letter in zip(courses, string.ascii_uppercase):
                course["course_code_suffix"] = letter
        raw_courses_3.extend(courses)
    raw_courses = raw_courses_3
    courses = []
    for raw_course in raw_courses:
        try:
            courses.append(process_course(raw_course, term))
        except ScrapeError:
            util.log_verbose(
                "Failed to parse course: {}"
                .format(repr(format_raw_course(raw_course))))
            num_failed += 1
    if num_failed >= 10:
        raise ScrapeError("Too many malformed courses: {}".format(num_failed))
    num_succeeded = len(raw_courses) - num_failed
    if num_succeeded < 500:
        raise ScrapeError("Not enough courses: {}".format(num_succeeded))
    util.log_verbose("Added descriptions to {} out of {} courses"
                     .format(num_descs_added, num_succeeded))
    return courses, term
