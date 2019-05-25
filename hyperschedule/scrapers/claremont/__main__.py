"""
Main entry point for the HMC course scraper. See __init__.py.
"""

import json
import sys

import hyperschedule.scrapers.claremont as scraper

if __name__ == "__main__":
    try:
        old_course_data = json.load(sys.stdin)
        old_courses = old_course_data["courses"] if old_course_data else None
        new_course_data = scraper.get_course_data(old_courses)
        json.dump(new_course_data, sys.stdout, indent=2)
    except KeyboardInterrupt:
        sys.exit(1)
