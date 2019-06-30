"""
Module that interfaces with Dead Man's Snitch to generate alerts
when the scraper stops sending us data.
"""

import datetime

import requests

import hyperschedule.util

from hyperschedule.util import Unset

# URL to GET when hearing from the scraper.
WEBHOOK_URL = "https://nosnch.in/f08b6b7be5"

# Don't GET the webhook more than one every this many seconds.
WEBHOOK_RATE_LIMIT = 5 * 60

# Number of seconds to wait before timing out webhook GET request.
WEBHOOK_TIMEOUT = 5

class Webhook:
    """
    Class that wraps a webhook by providing rate-limiting
    functionality.
    """

    def __init__(self, url, rate_limit):
        """
        Construct a new `Webhook` which sends a GET to `url` at most once
        every `rate_limit` seconds.
        """
        self.url = url
        self.rate_limit = rate_limit
        self.timestamp = Unset

    def get(self):
        """
        Send a GET request to the provided `url`. If it has been less than
        `rate_limit` seconds since the last request, silently do
        nothing. If the request errors out, raise a subclass of
        `requests.exceptions.RequestException`.
        """
        if self.timestamp is not Unset:
            timestamp = datetime.datetime.now().timestamp()
            if timestamp - self.timestamp < self.rate_limit:
                return
            self.timestamp = timestamp
        resp = requests.get(self.url)
        resp.raise_for_status()

webhook = Webhook(url=WEBHOOK_URL, rate_limit=WEBHOOK_RATE_LIMIT)

def report_success():
    """
    Report successful scraping to Dead Man's Snitch.
    """
    if hyperschedule.util.get_env_boolean("snitch"):
        webhook.get()
