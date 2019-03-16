def schedule_sort_key(slot):
    return slot["days"], slot["startTime"], slot["endTime"]

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
