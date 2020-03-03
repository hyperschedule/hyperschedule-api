"""
Module with utility functions used by both the Portal and Lingk
scrapers.

Course codes at the Claremont Colleges are composed from several
individual components. This module has functions that transform this
set of components between various different representations, including
a string, a dictionary, and a list. There are two different types of
course codes: ones that include a section number, and ones that do
not. Both are used, so several functions in this module handle both by
means of the `with_section` boolean parameter.
"""

import re

from hyperschedule.util import ScrapeError

# Regex used to match a Portal/Lingk course code (see
# `parse_course_code`).
COURSE_REGEX = r"([A-Z]+) *?([0-9]+) *([A-Z]*[0-9]?) *([A-Z]{2})(?:-([0-9]+))?"


def parse_course_code(course_code, with_section):
    """
    Given a course code in the format used by Portal and Lingk, with
    or without a section number ("PHIL 179A HM-01" or just "PHIL179A
    HM") as controlled by `with_section`, parse it and return a
    dictionary with keys:

    - department (string)
    - course_number (integer)
    - course_code_suffix (string)
    - school (string)
    - section (integer, or null if with_section is false)

    The given course code may also be in the format returned by
    `course_info_as_string`.

    Throw ScrapeError if parsing fails.
    """
    match = re.match(COURSE_REGEX, course_code)
    if not match:
        raise ScrapeError("malformed course code: {}".format(repr(course_code)))
    department, course_number, num_suffix, school, section = match.groups()
    if not department:
        raise ScrapeError("empty string for department")
    if "/" in department:
        raise ScrapeError("department contains slashes: {}".format(repr(department)))
    try:
        course_number = int(course_number)
    except ValueError:
        raise ScrapeError("malformed course number: {}".format(repr(course_number)))
    if course_number <= 0:
        raise ScrapeError("non-positive course number: {}".format(course_number))
    if "/" in num_suffix:
        raise ScrapeError(
            "course code suffix contains slashes: {}".format(repr(num_suffix))
        )
    if not school:
        raise ScrapeError("empty string for school")
    if "/" in school:
        raise ScrapeError("school contains slashes: {}".format(repr(school)))
    if bool(section) != bool(with_section):
        if with_section:
            raise ScrapeError("section missing")
        else:
            raise ScrapeError("section unexpectedly present: {}".format(repr(section)))
    if section:
        try:
            section = int(section)
        except ValueError:
            raise ScrapeError("malformed section number: {}".format(repr(section)))
        if section <= 0:
            raise ScrapeError("non-positive section number: {}".format(section))
    # If section is None, just leave it as is.
    return {
        "department": department,
        "courseNumber": course_number,
        "courseCodeSuffix": num_suffix,
        "school": school,
        "section": section,
    }


def course_info_as_string(course_info):
    """
    Given a dictionary as returned by `parse_course_code` with
    `with_section` true, return a course code string that can be used
    on the frontend.

    Throw ScrapeError if the course code is malformed.
    """
    assert course_info["section"]
    return "{} {:03d}{} {}-{:02d}".format(
        course_info["department"],
        course_info["courseNumber"],
        course_info["courseCodeSuffix"],
        course_info["school"],
        course_info["section"],
    )


def course_info_as_list(course_info, with_section):
    """
    Given a dictionary as returned by `parse_course_code`, return a
    list that can be used on the frontend as a sort key
    (`with_section` true) or mutual exclusion key (`with_section`
    false). If the `with_section` argument to this function is true,
    then the `course_info` must have been generated with
    `with_section` true.
    """
    assert not (bool(with_section) and not bool(course_info["section"]))
    lst = [
        course_info["department"],
        course_info["courseNumber"],
        course_info["courseCodeSuffix"],
        course_info["school"],
    ]
    if with_section:
        lst.append(course_info["section"])
    return lst


def parse_term_code(term):
    """
    Given a term code (e.g. "FA 2018"), return a dictionary with keys:

    * year (integer)
    * fall (boolean)
    * spring (boolean)
    """
    match = re.match(r"(FA|SP)\s*(20[0-9]{2})", term)
    if not match:
        raise ScrapeError("malformed term code: {}".format(repr(term)))
    return {
        "year": int(match.group(2)),
        "fall": match.group(1) == "FA",
        "spring": match.group(1) == "SP",
    }


def term_info_as_list(term_info):
    """
    Given a dictionary as returned by `parse_term_code`, return a list
    suitable for use as a sort key.
    """
    return [term_info["year"], term_info["spring"]]


def term_info_as_display_name(term_info):
    """
    Given a dictionary as returned by `parse_term_code`, return a
    string suitable for use as a display name.
    """
    return "{} {}".format("Fall" if term_info["fall"] else "Spring", term_info["year"])
