"""
Module for validating course data that we get from scrapers.
"""

from hyperschedule.api.util import UserError

def check(data):
    """
    Validate that data posted to /api/v4/courses is well-formed.
    """
    if not isinstance(data, dict):
        raise UserError("data is not a map: {}".format(data))
    scraper = data["scraper"]
    if not isinstance(scraper, str):
        raise UserError("scraper ID is not a string: {}".format(scraper))
    term_info = data["term"]
    if not isinstance(term_info, dict):
        raise UserError("term info is not a map: {}".format(term_info))
    for key in ("termCode", "termName"):
        if not isinstance(term_info.get(key), str):
            raise UserError("{} is not a string: {}".format(
                key, term_info.get(key),
            ))
    if not isinstance(term_info["termSortKey"], list):
        raise UserError("termSortKey is not an array: {}".format(
            term_info["termSortKey"],
        ))
    for item in term_info["termSortKey"]:
        if not isinstance(item, (bool, int, str)):
            raise UserError("termSortKey contains non-primitive: {}".format(
                item,
            ))
    # TODO: validate courses
