#!/usr/bin/env python3

from selenium import webdriver
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
import datetime as dt
import re
import json
import os

os.environ['PATH'] = './node_modules/.bin:' + os.environ.get('PATH', '')

browser = webdriver.PhantomJS()

try:
    url = 'https://portal.hmc.edu/ICS/Portal_Homepage.jnz?portlet=Course_Schedules&screen=Advanced+Course+Search&screenType=next'
    browser.get(url)

    term_dropdown = Select(browser.find_element_by_id('pg0_V_ddlTerm'))
    term_names = [option.text for option in term_dropdown.options]
    terms = []
    for term_name in term_names:
        match = re.match(r'\s*(FA|SP)\s*([0-9]{4})\s*', term_name)
        if match:
            fall_or_spring, year_str = match.groups()
            terms.append((int(year_str), fall_or_spring == 'FA', term_name))
    assert terms, "Couldn't parse any term names (from: {})".format(repr(term_names))
    most_recent_term = max(terms)
    term_dropdown.select_by_visible_text(most_recent_term[2])

    title = browser.find_element_by_id('pg0_V_txtTitleRestrictor')
    title.clear()
    title.send_keys('*')

    search = browser.find_element_by_id('pg0_V_btnSearch')
    search.click()

    show_all = browser.find_element_by_id('pg0_V_lnkShowAll')
    show_all.click()

    html = browser.page_source
finally:
    browser.quit()

soup = BeautifulSoup(html, 'lxml')

table = soup.find(id='pg0_V_dgCourses')
body = table.find('tbody')
rows = body.find_all('tr', recursive=False)

raw_courses = []

for row in rows:
    if 'style' in row.attrs and row.attrs['style'] == 'display:none;':
        continue
    elements = row.find_all('td')
    add, course_code, name, faculty, seats, status, schedule, credits, begin, end = elements
    raw_courses.append({
        'course_code': course_code.text,
        'course_name': name.text,
        'faculty': faculty.text,
        'seats': seats.text,
        'status': status.text,
        'schedule': [stime.text for stime in schedule.find_all('li')],
        'credits': credits.text,
        'begin_date': begin.text,
        'end_date': end.text,
    })

courses = []

def schedule_sort_key(slot):
    return slot['days'], slot['startTime'], slot['endTime'], slot['days']

def days_sort_key(day):
    return 'MTWRFSU'.index(day)

for raw_course in raw_courses:
    course_code = raw_course['course_code'].strip()
    course_regex = r'([A-Z]+) *?([0-9]+) *([A-Z]*[0-9]?) *([A-Z]{2})-([0-9]+)'
    department, course_number, num_suffix, school, section = re.match(
        course_regex, course_code).groups()
    course_number = int(course_number)
    section = int(section)
    course_name = raw_course['course_name'].strip()
    faculty = re.split(r'\s*\n\s*', raw_course['faculty'].strip())
    faculty = list(set(faculty))
    faculty.sort()
    open_seats, total_seats = map(
        int, re.match(r'([0-9]+)/([0-9]+)', raw_course['seats']).groups())
    course_status = raw_course['status'].lower()
    schedule_regex = r'(?:([MTWRFSU]+)\xa0)?([0-9]+:[0-9]+(?: ?[AP]M)?) - ([0-9]+:[0-9]+ ?[AP]M); ([A-Za-z0-9, ]+)'
    schedule = []
    for slot in raw_course['schedule']:
        if slot.startswith('0:00 - 0:00 AM'):
            continue
        match = re.match(schedule_regex, slot)
        assert match, ("Couldn't parse schedule: " + repr(slot) +
                       ' (for course {})'.format(repr(course_code)))
        days, start, end, location = match.groups()
        if days:
            days = list(set(days))
            assert days
            for day in days:
                assert day in 'MTWRFSU'
            days.sort(key=days_sort_key)
            days = ''.join(days)
        else:
            days = []
        if not start.endswith('AM') or start.endswith('PM'):
            start += end[-2:]
        start = parse_date(start).time()
        end = parse_date(end).time()
        location = ' '.join(location.strip().split())
        # API uses camelCase since the rest is in JavaScript
        schedule.append({
            'days': days,
            'location': location,
            'startTime': start.strftime('%H:%M'),
            'endTime': end.strftime('%H:%M'),
        })
    schedule.sort(key=schedule_sort_key)
    quarter_credits = round(float(raw_course['credits']) / 0.25)
    begin_date = parse_date(raw_course['begin_date']).date()
    end_date = parse_date(raw_course['end_date']).date()
    # First half-semester courses start (spring) January 1 through
    # January 31 or (fall) July 15 through September 15. (For some
    # reason, MATH 30B in Fall 2017 is listed as starting August 8.)
    first_half = (dt.date(begin_date.year, 1, 1) <
                  begin_date <
                  dt.date(begin_date.year, 1, 31)
                  or
                  dt.date(begin_date.year, 7, 15) <
                  begin_date <
                  dt.date(begin_date.year, 9, 15))
    # Second half-semester courses for the spring end May 1 through
    # May 31, but there's also frosh chem pt.II which just *has* to be
    # different by ending 2/3 of the way through the semester. So we
    # also count that by allowing April 1 through April 30. Sigh. Fall
    # courses end December 1 through December 31.
    second_half = (dt.date(end_date.year, 4, 1) <
                   end_date <
                   dt.date(end_date.year, 5, 31)
                   or
                   dt.date(end_date.year, 12, 1) <
                   end_date <
                   dt.date(end_date.year, 12, 31))
    assert first_half or second_half, ("Weird course start/end dates (for course {})"
                                       .format(repr(course_code)))
    courses.append({
        'department': department,
        'courseNumber': course_number,
        'courseCodeSuffix': num_suffix,
        'school': school,
        'section': section,
        'courseName': course_name,
        'faculty': faculty,
        'openSeats': open_seats,
        'totalSeats': total_seats,
        'courseStatus': course_status,
        'schedule': schedule,
        'quarterCredits': quarter_credits,
        'firstHalfSemester': first_half,
        'secondHalfSemester': second_half,
        'startDate': begin_date.strftime('%Y-%m-%d'),
        'endDate': end_date.strftime('%Y-%m-%d'),
    })

def course_sort_key(course):
    return (
        course['department'],
        course['courseNumber'],
        course['courseCodeSuffix'],
        course['school'],
        course['section'],
    )

courses.sort(key=course_sort_key)

with open('courses.json.tmp', 'w') as f:
    json.dump(courses, f)

os.rename('courses.json.tmp', 'courses.json')
