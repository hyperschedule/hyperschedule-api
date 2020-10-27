"""
Module that handles running the scraper repeatedly and generating
diffs that can be returned from the API.

The diff format used internally by this module is documented in the
README, except that we don't have any special cases for e.g. the
"error" and "until" keys (those are added on by the API module at a
higher level). See `compute_diff`.
"""

import datetime
import json
import os
import pathlib
import subprocess
import threading
import traceback
import itertools

import atomicwrites
import boto3
import botocore.exceptions
import requests
import requests.exceptions

import hyperschedule
import hyperschedule.util as util
import hyperschedule.database as database

from hyperschedule.util import ScrapeError, Unset

# Number of seconds to wait between attempts to run the scraper.
# hotfix, to "pause" hyperschedule scrape data, by scraping only once a day
SCRAPER_REPEAT_DELAY = 86400 # 5

# URL to GET on scraper success.
WEBHOOK_URL = "https://nosnch.in/f08b6b7be5"

# Number of seconds to wait before timing out webhook GET request.
WEBHOOK_TIMEOUT = 5

# Path to JSON file where scraper data is cached if 'cache' config var
# is enabled.
CACHE_FILE = hyperschedule.ROOT_DIR / "out" / "courses.json"


def list_startswith(lst, prefix):
    """
    Check whether `lst` starts with the given `prefix` list.
    """
    return len(prefix) <= len(lst) and all(a == b for a, b in zip(lst, prefix))


def compute_diff(old, new):
    """
    Compute a diff that, when applied to object `old`, will give object
    `new`. Do not modify `old` or `new`.
    """
    if not isinstance(old, dict) or not isinstance(new, dict):
        return new
    diff = {}
    for key, val in new.items():
        if key not in old:
            diff[key] = val
        elif old[key] != val:
            diff[key] = compute_diff(old[key], val)
    for key in old:
        if key not in new:
            diff[key] = "$delete"
    return diff


def apply_diff(obj, diff):
    """
    Apply the diff `diff` to object `obj`, returning a new object.
    """
    if not isinstance(obj, dict) or not isinstance(diff, dict):
        return diff
    obj = dict(obj)
    for key, val in diff.items():
        if val == "$delete":
            try:
                obj.pop(key)
            except KeyError:
                pass
            continue
        if key not in obj:
            obj[key] = val
            continue
        obj[key] = apply_diff(obj[key], val)
    return obj


def merge_diffs(d1, d2):
    """
    Merge diffs `d1` and `d2`, returning a new diff which is
    equivalent to applying both diffs in sequence. Do not modify `d1`
    or `d2`.
    """
    if not isinstance(d1, dict) or not isinstance(d2, dict):
        return d2
    diff = d1.copy()
    for key, val in d2.items():
        diff[key] = merge_diffs(diff[key], val) if key in diff else val
    return diff


class DiffManager:
    """
    Class for managing a series of updates to a data object. The
    abstraction provided is as follows. The class holds one "current"
    data object, which you can update via the `set_current_data`
    method. At each update, you provide an age (some integer, e.g. the
    UNIX timestamp). Then, the class stores enough bookkeeping
    information that you can later ask for a diff of the data object
    from any past age to the present. However, internal pruning
    ensures only logarithmic memory usage is necessary to allow for
    computing a diff from *any* past age.

    Thread-safe for one writer (`set_current_data`) and any number of
    readers (`get_current_data`, `get_diff_to_present`).
    """

    def __init__(self):
        """
        Construct empty diff manager. The next step is to call
        `set_current_data` with initial data object.
        """
        # (age, data, [(age, diff), ...])
        self.state = (Unset, Unset, [])

    def set_current_data(self, new_age, new_data):
        """
        Initialize or update data object.
        """
        current_age, current_data, diffs = self.state
        if diffs:
            # Prune old updates. We keep at least one diff in the last
            # time step, at least one in the last two, at least one in
            # the last four, and so on. This guarantees logarithmic
            # memory usage.
            diffs = list(diffs)
            long_enough_to_keep = 1
            for i in reversed(range(len(diffs))):
                old_age, old_diff = diffs[i]
                if new_age - old_age < long_enough_to_keep:
                    diffs.pop(i)
                else:
                    long_enough_to_keep *= 2
        if current_data is not Unset:
            # Push new diff and update old diffs.
            new_diff = compute_diff(current_data, new_data)
            diffs.append((current_age, {}))
            diffs = [
                (old_age, merge_diffs(old_diff, new_diff))
                for (old_age, old_diff) in diffs
            ]
        self.state = new_age, new_data, diffs

    def get_current_data(self):
        """
        Get a tuple of (current age, current data object). If
        `set_current_data` has never been called, both values are
        `util.Unset`.
        """
        return self.state[:2]

    def get_diff_to_present(self, since):
        """
        Get the diff from the given timestamp to the present. The idea is
        that if `get_current_age` returned the value you pass as
        `since`, then applying the returned diff to the corresponding
        value of `get_current_data` at that time will give you the
        *current* value of `get_current_data`.

        If `set_current_data` has never been called, return
        `util.Unset`. Otherwise, always return a valid diff.

        Return a tuple (diff, full, current_age), where `full` is a
        boolean which (if true) indicates that the diff is not
        actually a diff, but should rather be considered the full,
        canonical data structure.
        """
        current_age, current_data, diffs = self.state
        if current_data is Unset:
            return Unset, Unset, Unset
        if since >= current_age:
            return {}, False, current_age
        for age, diff in reversed(diffs):
            if since >= age:
                return diff, False, current_age
        return current_data, True, current_age


class DiffWorker:
    """
    Class abstracting doing a repeated computation in a separate
    thread and updating a `DiffManager`.
    """

    def __init__(self, compute_data, repeat_delay, initial_data=Unset):
        """
        Construct new `DiffWorker`. `compute_data` is a function that
        takes the old data (or `util.Unset`) and returns the data
        which will be passed to the `DiffManager` (unless the return
        value is `util.Unset`). `repeat_delay` is the number of
        seconds to wait between each call to `compute_data`.
        `initial_data`, if provided, is passed as an initial value to
        the `DiffManager`.
        """
        self.compute_data = compute_data
        self.repeat_delay = repeat_delay
        self.diff_manager = DiffManager()
        if initial_data is not Unset:
            age = int(datetime.datetime.now().timestamp())
            self.diff_manager.set_current_data(age, initial_data)

        def target():
            _, old_data = self.diff_manager.get_current_data()
            data = self.compute_data(old_data)
            if data is not Unset:
                age = int(datetime.datetime.now().timestamp())
                self.diff_manager.set_current_data(age, data)
            self.timer = threading.Timer(self.repeat_delay, target)
            self.timer.start()

        # If we don't set the thread as a daemon then it keeps our
        # Gunicorn workers alive after Gunicorn is killed. Ew!!
        self.thread = threading.Thread(target=target, daemon=True)

    def start(self):
        """
        Start the first call to `compute_data`.
        """
        self.thread.start()

    def get_current_data(self):
        """
        Call `get_current_data` on the underlying `DiffManager`.
        """
        return self.diff_manager.get_current_data()

    def get_diff_to_present(self, since):
        """
        Call `get_diff_to_present` on the underlying `DiffManager`.
        """
        return self.diff_manager.get_diff_to_present(since)


def rate_limited(rate_limit):
    """
    Decorator to rate-limit a function. This means that if you call
    the function less than `rate_limit` seconds after the last time
    you called it, then the new call is simply ignored.
    """

    def decorate(fn):
        last_timestamp = Unset

        def decorated(*args, **kwargs):
            nonlocal last_timestamp
            timestamp = datetime.datetime.now().timestamp()
            if last_timestamp is not Unset:
                if timestamp - last_timestamp < rate_limit:
                    return
            last_timestamp = timestamp
            return fn(*args, **kwargs)

        return decorated

    return decorate


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

        @rate_limited(rate_limit)
        def get():
            resp = requests.get(self.url)
            resp.raise_for_status()

        self._get = get

    def get(self):
        """
        Send a GET request to the provided `url`. If it has been less than
        `rate_limit` seconds since the last request, silently do
        nothing. If the request errors out, raise a subclass of
        `requests.exceptions.RequestException`.
        """
        return self._get()


def try_compute_data(s3, webhook, old_data):
    """
    Try to run the scraper and return course data. If something goes
    wrong, raise `ScrapeError`. Otherwise, invoke the provided
    `Webhook`. `old_data` is the previous course data or `util.Unset`.
    """
    scraper_timeout = util.get_env("scraper_timeout")
    try:
        scraper_timeout = int(scraper_timeout)
        if scraper_timeout <= 0:
            raise ValueError
    except ValueError:
        util.warn("Illegal scraper timeout: {}".format(repr(scraper_timeout)))
        util.log("Resetting timeout to 60 seconds")
        os.environ["HYPERSCHEDULE_SCRAPER_TIMEOUT"] = "60"
        scraper_timeout = 60
    if old_data is util.Unset:
        # For JSON.
        old_data = None
    try:
        util.log("Running scraper")
        process = subprocess.Popen(
            ["python", "-m", "hyperschedule.scrapers.claremont"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        output, _ = process.communicate(
            input=json.dumps(old_data).encode(), timeout=scraper_timeout
        )
        if process.returncode != 0:
            raise ScrapeError("scraper failed")
        try:
            output = output.decode()
        except UnicodeDecodeError as e:
            raise ScrapeError(
                "scraper emitted malformed output: {}".format(e)
            ) from None
        if "$delete" in output:
            raise ScrapeError("scraper output contains '$delete'")
        data = json.loads(output)
        if util.get_env_boolean("snitch"):
            webhook.get()
        if util.get_env_boolean("cache"):
            cache_file_write(data)
        if util.get_env_boolean("s3_write"):
            s3_write(s3, data)
    except OSError as e:
        raise ScrapeError(
            "unexpected error while running scraper: {}".format(e)
        ) from None
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise ScrapeError(
            "scraper timed out after {} seconds".format(scraper_timeout)
        ) from None
    except json.decoder.JSONDecodeError:
        raise ScrapeError("scraper did not return valid JSON") from None
    except requests.exceptions.RequestException as e:
        util.warn("failed to reach success webhook: {}".format(e))
    database.merge_syllabus_info_to_courses(data)
    return data


def compute_data(s3, webhook, old_data):
    """
    Try to run the scraper and return course data (see
    `try_compute_data`). If something goes wrong, log the error and
    return `util.Unset`.
    """
    try:
        data = try_compute_data(s3, webhook, old_data)
        util.log("Scraper succeeded")
        return data
    except ScrapeError as e:
        util.log(str(e).capitalize())
        return Unset
    except Exception:
        util.log("Unexpected error:")
        traceback.print_exc()
        return Unset


def cache_file_read():
    """
    Read and return data from the scraper result cache file. If this
    fails, log the error and return `util.Unset`.
    """
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except OSError as e:
        if CACHE_FILE.is_file():
            util.warn("Failed to read cache file: {}".format(e))
    except json.decoder.JSONDecodeError:
        util.warn("Cache file contained invalid JSON")
    return Unset


def cache_file_write(data):
    """
    Write provided `data` to cache file, atomically. If this fails,
    log the error.
    """
    f = None
    try:
        with atomicwrites.atomic_write(CACHE_FILE, overwrite=True) as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    except OSError as e:
        util.warn("Failed to write cache file: {}".format(e))
    finally:
        if f:
            try:
                # Clean up in case of error, since we passed
                # delete=False.
                pathlib.Path(f.name).unlink()
            except OSError:
                pass


S3_BUCKET = "hyperschedule"
S3_KEY = "courses.json"
S3_RATE_LIMIT = 5 * 60  # seconds


def s3_read(s3):
    """
    Read and return data from the scraper result S3 bucket. If this
    fails, log the error and return `util.Unset`. `s3` is a boto3 S3
    resource.
    """
    try:
        obj = s3.Object(S3_BUCKET, S3_KEY)
        return json.load(obj.get()["Body"])
    except (
        botocore.exceptions.BotoCoreError,
        botocore.exceptions.ClientError,
        json.JSONDecodeError,
    ) as e:
        util.warn("Failed to read S3: {}".format(e))
        return Unset


@rate_limited(S3_RATE_LIMIT)
def s3_write(s3, data):
    """
    Write provided `data` to S3 bucket. If this fails, log the error.
    `s3` is a boto3 S3 resource.
    """
    try:
        obj = s3.Object(S3_BUCKET, S3_KEY)
        obj.put(Body=json.dumps(data).encode())
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as e:
        util.warn("Failed to write S3: {}".format(e))


class HyperscheduleWorker(DiffWorker):
    """
    Class abstracting the Hyperschedule background scraper task.
    Create it and then call `start`.
    """

    def __init__(self):
        """
        Construct new instance of the scraper task. Start it by calling
        `start`.
        """
        cache = util.get_env_boolean("cache")
        initial_data = cache_file_read() if cache else Unset
        if util.get_env_boolean("s3_read") or util.get_env_boolean("s3_write"):
            s3 = boto3.resource("s3")
        else:
            s3 = Unset
        if initial_data is Unset and util.get_env_boolean("s3_read"):
            initial_data = s3_read(s3)
        webhook = Webhook(WEBHOOK_URL, WEBHOOK_TIMEOUT)
        util.log(
            "Starting worker (on-disk cache {}, S3 {})".format(
                "enabled" if cache else "disabled",
                "enabled" if s3 is not Unset else "disabled",
            )
        )
        super().__init__(
            lambda old_data: compute_data(s3, webhook, old_data),
            SCRAPER_REPEAT_DELAY,
            initial_data=initial_data,
        )
