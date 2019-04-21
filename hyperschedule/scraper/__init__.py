"""
Course scraper for HMC Portal and Lingk. Combines data from the
two sources to get course descriptions.
"""

import re
import traceback

import psutil

import hyperschedule.scraper.lingk as lingk
import hyperschedule.scraper.portal as portal
import hyperschedule.scraper.shared as shared
import hyperschedule.util as util

from hyperschedule.util import ScrapeError

def kill_google_chrome():
    """
    Kill all currently running Google Chrome processes. This is
    important to save memory, and also to avoid a memory leak if
    Selenium does not shut down cleanly.

    If config var 'kill_orphans' is not enabled, do nothing.
    """
    if not util.get_env_boolean("kill_orphans"):
        return
    for proc in psutil.process_iter():
        # We have to kill the helpers, too -- on Heroku we are using
        # Docker without baseimage-docker and thus zombie children
        # don't get reaped correctly; see
        # <https://blog.phusion.nl/2015/01/20/docker-and-the-pid-1-zombie-reaping-problem/>.
        if re.match(r"chrome", proc.name(), re.IGNORECASE):
            util.log("Killing {} process {}"
                     .format(repr(proc.name()), proc.pid))
            proc.kill()

def course_to_key(course):
    """
    Given a course object, return a tuple that can be used to index
    into the course description dictionary returned by
    `lingk.get_course_descriptions`.
    """
    course_info = shared.parse_course_code(
        course["courseCode"], with_section=False)
    return tuple(shared.course_info_as_list(course_info, with_section=False))

def get_course_data(old_courses):
    """
    Return data structure for the API given the list of old courses
    (or None).
    """
    # Do this ahead of time (1) to save on memory, and (2) to avoid
    # messing up the connection pool when we kill later.
    kill_google_chrome()
    try:
        desc_index = lingk.get_course_descriptions()
    except ScrapeError:
        util.log("Got error while scraping Lingk:")
        traceback.print_exc()
        desc_index = {}
        if old_courses:
            util.log("Using previously scraped course descriptions")
            for course in old_courses.values():
                desc = course["courseDescription"]
                if not desc:
                    continue
                key = course_to_key(course)
                desc_index[key] = desc
    courses, term = portal.get_courses(desc_index)
    term_info = shared.parse_term_code(term)
    term_name = shared.term_info_as_display_name(term_info)
    term_sort_key = shared.term_info_as_list(term_info)
    return {
        "terms": {
            term: {
                "termCode": term,
                "termSortKey": term_sort_key,
                "termName": term_name,
            },
        },
        "courses": {
            course["courseCode"]: course for course in courses
        }
    }
