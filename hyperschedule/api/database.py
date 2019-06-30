"""
Module that handles keeping track of course data persistently and
computing diffs.
"""

import collections
import datetime
import threading

import hyperschedule.api.diff

from hyperschedule.api.util import UserError
from hyperschedule.util import Unset

class Database:

    def _read_from_disk(self):
        """
        Attempt to read the state of the database from disk. If this
        fails, do nothing. Log a warning if the file(s) exist on disk
        but loading fails.
        """
        hyperschedule.util.warn("Reading from disk not yet implemented")
        pass

    def _write_to_disk(self):
        """
        Attempt to write the state of the database to disk. If this fails,
        log a warning and do nothing.
        """
        hyperschedule.util.warn("Writing to disk not yet implemented")
        pass

    def __init__(self):
        """
        Initialize a new database. Attempt to read existing data from
        disk.
        """
        c1 = hyperschedule.api.diff.DiffManager
        c2 = lambda: collections.defaultdict(c1)
        self.diff_managers = collections.defaultdict(c2)
        self.terms = collections.defaultdict(dict)
        self.most_recent_terms = {}
        self.lock = threading.Lock()
        self._read_from_disk()

    def set_current_data(self, scraper_id, term_data, courses):
        """
        Receive course data from a scraper. `scraper_id` is a string,
        `term_data` is a map in the format of the "term" field of API
        v4, and `courses` is a map in the format of the "courses"
        field of API v4.
        """
        timestamp = int(datetime.datetime.now().timestamp())
        term_code = term_data["termCode"]
        with self.lock:
            self.diff_managers[scraper_id][term_code].set_current_data(
                timestamp, courses,
            )
            self.terms[scraper_id][term_code] = term_data
            term_list = self.terms[scraper_id].values()
            self.most_recent_terms[scraper_id] = (
                max(term_list, key=lambda t: t["termSortKey"])
            )
            self._write_to_disk()

    def _get_diff_manager(self, scraper_id, term_code):
        """
        Get the diff manager for a given scraper and term.
        """
        if scraper_id not in self.diff_managers:
            raise UserError("no such scraper: {}".format(scraper_id))
        if term_code not in self.diff_managers[scraper_id]:
            raise UserError("no such term: {}".format(term_code))
        return self.diff_managers[scraper_id][term_code]

    def get_diff_to_present(
            self, scraper_id, since=Unset,
            current_term_code=Unset, requested_term_code=Unset,
    ):
        """
        Get the diff to the present for a given scraper. If `since` is
        `Unset`, always return the latest data. Otherwise, try to
        return a diff. If `since` is set, then `current_term_code`
        must also be set to the code of the term to which the client's
        current course data corresponds. In that case, a diff can only
        be returned if the new course data is in the same term as the
        old course data. `requested_term_code` is the term from which
        to return course data, defaulting to the latest term.
        """
        with self.lock:
            if scraper_id not in self.most_recent_terms:
                raise UserError("data not available yet", code=503)
            if requested_term_code is Unset:
                requested_term_code = (
                    self.most_recent_terms[scraper_id]["termCode"]
                )
            if current_term_code != requested_term_code:
                since = Unset
            diff_manager = self._get_diff_manager(
                scraper_id, requested_term_code,
            )
            return (
                *diff_manager.get_diff_to_present(since=since),
                self.terms[scraper_id][requested_term_code],
            )
