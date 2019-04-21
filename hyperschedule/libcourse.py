"""
Module with shared constants and utility functions related to
(canonical) course object processing.

There are two types of canonical course objects: full and partial. The
partial ones have a subset of the keys of the full ones, namely only
the keys corresponding to the course code.
"""

import re

from hyperschedule.util import ScrapeError

def schedule_sort_key(slot):
    """
    Given a schedule slot map from a canonical course object, return a
    sort key (a tuple, in fact).
    """
    return slot["days"], slot["startTime"], slot["endTime"]

COURSE_ATTRS = [
    "courseCodeSuffix",
    "courseDescription",
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
    """
    Given a (full *or* partial) canonical course object, return a
    string that can be used to uniquely identify it, and to index it.
    """
    return "/".join(str(course[attr]) for attr in COURSE_INDEX_ATTRS)

def course_from_index_key(key):
    """
    Given an index key as created by course_to_index_key, return a
    *partial* canonical course object containing the fields which can
    be reconstructed from the index key.
    """
    course = {}
    for attr, value in zip(COURSE_INDEX_ATTRS, key.split("/")):
        if COURSE_INDEX_ATTRS_CONVERT_TO_INT[attr]:
            value = int(value)
        course[attr] = value
    return course

def course_sort_key(course):
    """
    Given a (full *or* partial) canonical course object, return a sort
    key for it (a tuple, in fact).
    """
    return tuple(course[attr] for attr in COURSE_INDEX_ATTRS)

def format_course(course):
    """
    Given a (full *or* partial) canonical course object, return a
    human-readable string representing it.
    """
    return "{} {:03d}{} {}-{:02d}".format(
        course["department"],
        course["courseNumber"],
        course["courseCodeSuffix"],
        course["school"],
        course["section"])

COURSE_REGEX = r"([A-Z]+) *?([0-9]+) *([A-Z]*[0-9]?) *([A-Z]{2})(?:-([0-9]+))?"

def parse_claremont_course_code(course_code):
    """
    Given a course code in the format used by Portal and Lingk, return
    a *partial* canonical course object containing the fields which
    can be extracted from it.

    The format is something like "PHIL179A HM-01", except the hyphen
    and section number may be omitted (in which case the corresponding
    value in the map will be None -- you must change the value to some
    positive integer for the object to be considered a valid partial
    course).
    """
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
    if section:
        try:
            section = int(section)
        except ValueError:
            raise ScrapeError(
                "malformed section number: {}".format(repr(section)))
        if section <= 0:
            raise ScrapeError(
                "non-positive section number: {}".format(section))
    # If section is None, just leave it as is.
    return {
        "department": department,
        "courseNumber": course_number,
        "courseCodeSuffix": num_suffix,
        "school": school,
        "section": section,
    }

FALL = "FA"
SPRING = "SP"

def format_term(term):
    """
    Given a term object (a dictionary with string "semester" and
    integer "year"), convert it to a string. This string is in the
    format used by the Lingk API.
    """
    return term["semester"] + str(term["year"])
