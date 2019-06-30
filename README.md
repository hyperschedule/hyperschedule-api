## Hyperschedule scraper

**Warning: README has not yet been updated to reflect major
architectural changes.**

This repository contains a Python webapp which scrapes information
from the [Claremont Colleges course catalog][portal] and exposes it
via a faster and more usable JSON API.

This service is used as the backend for the [Hyperschedule
webapp][frontend]. Since that webapp was previously hosted on the same
domain as the API, the service in this repository also serves a single
HTML page at the domain root which directs users to copy their data
and migrate to the new frontend domain.

You may see the service in action by visiting the following URL:

* <https://hyperschedule.herokuapp.com/api/v3/courses>

## API v3

The API exposes one endpoint,
`/api/v3/courses?school=hmc[&since=<timestamp>]`. This endpoint
returns data in JSON format, including a timestamp. This timestamp may
be passed to the same endpoint in future requests to receive a diff
(described below) instead of the full data.

### Full data format

The response is a map with keys:

* `data`: The course data.
* `until`: Integer which may be passed as the `since` parameter on
  subsequent requests.
* `error`: String with an error message, or null. No guarantees are
  made about the rest of the response if this key is non-null.
* `full`: Boolean indicating whether `data` is the full course data.
  Always true unless `since` is provided as a parameter in the API
  request. If false, then `data` should be interpreted as a diff, as
  per the next section.

The course data is a map with keys:

* `terms`: Map from term codes (`termCode`; see below) to *term
  objects*.
* `courses`: Map from course codes (`courseCode`; see below) to
  *course objects*.

Term objects are maps with keys:

* `termCode`: Short name or code for the term, string.
* `termSortKey`: List of JSON primitives indicating the sort order of
  this term.
* `termName`: Long or display name for the term, string.

Course objects are maps with keys:

* `courseCode`: Short name or code for the course, string.
* `courseName`: Long or display name for the course, string.
* `courseSortKey`: List of JSON primitives indicating the sort order
  of this course.
* `courseMutualExclusionKey`: List of JSON primitives which, if equal
  to the mutual exclusion key on another course, indicates that the
  two courses conflict (e.g. they are two sections of the same
  course).
* `courseDescription`: Course description, string or null.
* `courseInstructors`: List of course instructors, strings, or null.
* `courseTerm`: Term code, string.
* `courseSchedule`: List of *schedule objects*.
* `courseCredits`: Number of credits, string containing integer or
  floating-point number.
* `courseSeatsTotal`: Number of seats for class registration,
  non-negative integer or null.
* `courseSeatsFilled`: Number of seats filled during for class
  registration, non-negative integer or null.
* `courseWaitlistLength`: Length of waitlist for class registration,
  non-negative integer or null.
* `courseEnrollmentStatus`: Status of class registration, string or
  null.

Schedule objects are maps with keys:

* `scheduleDays`: String containing some subset of the characters
  `SMTWRFU` in that order, indicating which days the meeting is on.
* `scheduleStartTime`: String in 24-hour `HH:MM` format, indicating
  when the meeting starts.
* `scheduleEndTime`: String in 24-hour `HH:MM` format, indicating when
  the meeting ends.
* `scheduleStartDate`: String in `YYYY-MM-DD` format, indicating when
  on the calendar the meeting starts repeating, inclusive.
* `scheduleEndDate`: String `YYYY-MM-DD`, indicating when on the
  calendar the meeting stops repeating, inclusive.
* `scheduleTermCount`: Number of terms into which the semester is
  subdivided (e.g. `2` to support half-semester courses).
* `scheduleTerms`: List of non-negative integers indicating which
  terms during which the course meets (e.g. `[0]` or `[1]` for
  first-half and second-half courses).
* `scheduleLocation`: String indicating location of meeting.

Do not rely on maps returned by the API having only the keys described
above.

### Diff format and resolution

If you pass a `since` parameter to the API, you will get a response
mostly in the same format as above, except that `data` *may be* a diff
instead of the full course object (to see which, check `full`). The
diff format is very similar to the full data format, except:

* Some keys may be missing, at any level.
* Some values may be replaced, at any level, with the string
  `$delete`.

To apply the diff, work recursively from the top level, using the
following rules:

* If at least one of the current data and diff is not a map, replace
  the current data with the diff.
* If the current data and diff are both maps, iterate through the keys
  and values of both.
  * If a key is absent in the diff, leave the current data alone.
  * If a key is equal to `$delete` in the diff, remove the
    corresponding key and value in the current data, if present.
  * If a key is present in the diff but not equal to `$delete`:
    * If the corresponding key is missing from the current data, copy
      over the key and value from the diff.
    * If the corresponding key is already present in the current data,
      then apply the value in the diff as a diff to the value in the
      current data (i.e. recurse to the top of these instructions).

## Development

First, install the following dependencies:

* [Python 3][python]
* [Pipenv][pipenv]
* [ChromeDriver][chromedriver]

Then, install the Python dependencies into a virtualenv by running:

    $ pipenv install

You may start the server in development mode on `localhost:3000` by
running:

    $ make dev

If you are working on the WSGI configuration, it may also be useful to
test in mostly-production mode:

    $ make prod

(Some features are still disabled because they should not be run
locally. They are only enabled by `make heroku`, which should only be
run on Heroku.)

If you inspect the `Makefile`, you will see that these targets are
just wrappers for:

    $ pipenv run python -m hyperschedule.server [key=val ...]

Hyperschedule may be configured by setting environment variables or
passing command-line arguments. Setting the environment variable
`HYPERSCHEDULE_FOO=bar` is equivalent to passing the command-line
argument `foo=bar`. To pass custom configuration options other than
the ones in `make dev` or `make prod`, you can do this (or just set
environment variables):

    $ make [dev | prod] ARGS="key=val ..."

Here are the supported configuration options:

* `cache=(yes|no)`: Whether to cache course data on disk, so that when
  you start the server it can immediately serve data. Defaults to
  `yes` for `dev`, `no` for `prod`.
* `debug=(yes|no)`: Whether to use the Flask debugging server, or the
  Gunicorn WSGI server. Defaults to `yes` for `dev`, `no` for `prod`.
* `expose=(yes|no)`: Whether to allow access to the server to other
  hosts on the local network. Defaults to `no`. For security, do not
  enable this locally.
* `headless=(yes|no)`: Whether to use a headless instance of Chrome
  rather than launching a full graphical window. Defaults to `yes`.
* `kill_orphans=(yes|no)`: Whether to kill instances of Google Chrome
  that may be orphaned by an abnormal exit of Selenium. Defaults to
  `no`. Needed when running in constrained-memory environment. Do not
  enable this locally if you use Chrome as a web browser.
* `lingk=(yes|no)`: Whether to actually scrape the Lingk API, or
  whether to instead use a horrifying hack by which we parse a trashy
  CSV that the registrar manually emailed to me. The advantage of the
  former is that it's not totally horrifying. The advantage of the
  latter is that we get course descriptions for Fall 2019. Defaults to
  `yes`.
* `port=N`: The port for the server to listen on. Defaults to `3000`.
* `s3_read=(yes|no)`: Whether to read course data from Amazon S3 at
  startup if it is not available in the on-disk cache. Defaults to
  `no`.
* `s3_write=(yes|no)`: Whether to write course data to Amazon S3 after
  it is generated. Should only be enabled in production. Defaults to
  `no`.
* `scraper_timeout=N`: Number of seconds that the scraper is allowed
  to run before timing out. This includes all time that the scraper is
  running (both Portal and Lingk). Defaults to `60`.
* `snitch=(yes|no)`: Whether to contact [Dead Man's Snitch][dms] on a
  successful course data update. Defaults to `no`. Do **not** enable
  this locally.
* `verbose=(yes|no)`: Whether to print more messages which might be
  useful for debugging. Defaults to `yes`.

If you have configured `lingk=yes` (not recommended currently), then
to obtain course descriptions, you will need to set the environment
variables `HYPERSCHEDULE_LINGK_KEY` and `HYPERSCHEDULE_LINGK_SECRET`.
For security, you should do this in your [`.env`][dotenv] file rather
than by passing command-line arguments. To obtain an API key and
secret, contact [**@raxod502**][raxod502].

If you have configured `s3_read=yes`, then you will need to [configure
AWS credentials][aws-creds]. The easiest way to do this is to install
the [AWS CLI][aws-cli] and run `aws configure`. Contact
[**@raxod502**][raxod502] for credentials.

You may wish to restart the server automatically when the code is
changed. Install [`watchexec`][watchexec] and run:

    $ watchexec -r -e py "make dev"

Run the tests:

    $ make test

Run debugging commands (check the source code for details):

    $ pipenv run python -m hyperschedule.debug <cmd>

## Contributing

Please do! Refer to the [contributor guidelines][contributing] first.

[contributing]: CONTRIBUTING.md

[aws-cli]: https://aws.amazon.com/cli/
[aws-creds]: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html
[chromedriver]: http://chromedriver.chromium.org/
[dms]: https://deadmanssnitch.com/
[dotenv]: https://github.com/theskumar/python-dotenv
[frontend]: https://github.com/MuddCreates/hyperschedule
[pipenv]: https://docs.pipenv.org/
[portal]: https://portal.hmc.edu/ICS/Portal_Homepage.jnz?portlet=Course_Schedules&screen=Advanced+Course+Search&screenType=next
[python]: https://www.python.org/
[raxod502]: https://github.com/raxod502
[watchexec]: https://github.com/mattgreen/watchexec
