## Hyperschedule scraper

This repository contains a Python webapp which scrapes information
from the [Claremont Colleges course catalog][portal] and exposes it
via a faster and more usable JSON API.

This service is used as the backend for the [Hyperschedule
webapp][frontend]. Since that webapp was previously hosted on the same
domain as the API, the service in this repository also serves a single
HTML page at the domain root which directs users to copy their data
and migrate to the new frontend domain.

You may see the service in action by visiting the following URLs:

* <https://hyperschedule.herokuapp.com/api/v2/all-courses>
* <https://hyperschedule.herokuapp.com/>

## Service usage

The following endpoints are exposed:
* `/`
  * displays a static HTML page directing the user to copy their
    schedule data and migrate to [hyperschedule.io]
* `/api/v1/all-courses`
  * returns a JSON map with the following keys:
    * `courses`:
      * non-empty list of distinct course objects (see below)
    * `lastUpdate`:
      * non-empty human-readable string describing the time elapsed
        since the course list was last recomputed on the server
* `/api/v2/all-courses`
  * returns a JSON map with the following keys:
    * `courses`:
      * non-empty list of distinct course objects (see below)
    * `timestamp`:
      * integer UNIX timestamp representing the time at which the data
        was retrieved
    * `malformedCourseCount`:
      * non-negative integer giving the number of courses whose
        information was entered incorrectly by the registrar
* `/api/v2/courses-since/<timestamp>`
  * `<timestamp>` is an integer UNIX timestamp; this endpoint returns
    changes to the course list *since* that timestamp. It is expected
    that the value of this parameter is taken from the `timestamp`
    field in a previous query to the API.
  * returns a JSON map with the following keys:
    * `incremental`: boolean indicating whether an incremental update
      is possible (incremental update data is only stored on the
      server for approximately the last 30 minutes)
    * `courses` (only if `incremental` is `false`):
      * non-empty list of distinct course objects (see below)
    * `diff` (only if `incremental` is `true`):
      * JSON map with the following keys:
        * `added`:
          * list of maps, possibly empty, representing course objects
            that have been added since `<timestamp>`
        * `removed`:
          * list of maps, possibly empty, representing course objects
            that have been removed since `<timestamp>`. Only the keys
            necessary to distinctly identify the course (see below)
            are included.
        * `modified`:
          * list of maps, possibly empty, representing course objects
            that have been modified since `<timestamp>`. Only the keys
            necessary to distinctly identify the course (see below),
            as well as the keys which have changed, are included.
    * `timestamp`:
      * integer UNIX timestamp representing the time at which the data
        was retrieved
    * `malformedCourseCount`:
      * non-negative integer giving the number of courses whose
        information was entered incorrectly by the registrar
* `/api/v2/malformed-courses`
  * possibly empty list of strings representing malformed courses
    which are not included in the normal course listing (the length of
    this list equals the value of `malformedCourseCount` returned from
    the other endpoints). The format of these strings should not be
    relied upon.

Course objects are maps with the following keys:
* `courseCodeSuffix`
  * string, possibly empty, not containing any slashes
* `courseName`
  * non-empty string
* `courseNumber`
  * positive integer
* `courseStatus`
  * string, one of `open`, `closed`, or `reopened`
* `department`
  * non-empty string, not containing any slashes
* `endDate`
  * string in the format `YYYY-MM-DD`, representing a valid date
* `faculty`
  * non-empty list of non-empty strings
* `firstHalfSemester`
  * boolean
* `openSeats`
  * non-negative integer
* `quarterCredits`
  * non-negative integer
* `schedule`
  * list of maps, possibly empty, with keys:
    * `days`
      * non-empty string containing some subset of the characters
        `MTWRFSU` in that order, without duplicates
    * `endTime`
      * string in the format `hh:mm`, representing a valid 24-hour
        time
    * `location`
      * non-empty string
    * `startTime`
      * string in the format `hh:mm`, representing a valid 24-hour
        time
* `school`
  * non-empty string, not containing any slashes
* `secondHalfSemester`
  * boolean
* `section`
  * positive integer
* `startDate`
  * string in the format `YYYY-MM-DD`, representing a valid date
* `totalSeats`
  * non-negative integer

Two course objects are considered *distinct* if they have differing
values for at least one of `school`, `department`, `courseNumber`,
`courseCodeSuffix`, or `section`. Since none of these values are
allowed to contain slashes, they may be concatenated reversibly with
slashes to form a unique string key by which to index the course.

Additional fields may be added to existing endpoints without
incrementing the API version.

## Development

First, install the following dependencies:

* [Python 3][python]
* [Pipenv][pipenv]
* [ChromeDriver][chromedriver]

Then, install the Python dependencies into a virtualenv by running:

    $ pipenv install

You may start the server in development mode on `localhost:3000` by
running:

    $ pipenv run ./server.py --dev

To run in production mode instead, pass `--prod`. You can change the
port that the server listens on by exporting the environment variable
`PORT`. Further configuration may be achieved via command-line
arguments:

* `--[no-]headless`: Don't spawn a graphical Chrome window for the web
  scraping. Defaults to `--headless`. Change it if you wish to debug
  the web scraping.
* `--[no-]cache`: When the server starts up, try to read in the course
  data from `courses.json` in this directory. Whenever the course data
  is modified, write it back to that file. This allows the course data
  to persist across server restarts. Defaults to `--cache` in
  development, `--no-cache` in production. Warning: course data read
  from the cache file is *not* validated!
* `--[no-]scrape`: Run the web scraper, not just the server. Defaults
  to `--scrape`. Disable it and use the debug endpoints if you wish to
  test the incremental update logic.

You may wish to restart the server automatically when the code is
changed (this works especially well with `--cache`). Install
[`watchexec`][watchexec] and run:

    $ pipenv run watchexec -r -e py "./server.py --dev ..."

When running in development mode, additional endpoints are available.
These are especially useful for testing the incremental update logic.
It is recommended to use [HTTPie] to interact with them. You can reset
the course data to its initial state:

    $ http PUT localhost:3000/debug/reset

You can provide a JSON file of courses (in the format under the
`current` key in `courses.json`) and have it processed as if it were
scraped from Portal (the timestamp defaults to the current time on the
server):

    $ http PUT localhost:3000/debug/set-courses[/<timestamp>] @my-course-file.json

If the server was run with `--no-scrape`, it may be useful to trigger
a one-off scraping operation:

    $ http PUT localhost:3000/debug/scrape

A good way to test the incremental update logic is to start the server
with the scraper disabled:

    $ pipenv run ./server.py --dev --no-scrape

Then hit the `/debug/reset` endpoint to clear the course data, and get
an initial snapshot of the courses from Portal using `/debug/scrape`.
After that, you can use [`jq`][jq] to extract the course data into an
easily editable JSON file:

    $ cat course-data.json | jq .current > courses.json

Make whatever changes you would like, and then upload them using
`/debug/set-courses`. The resulting update diffs can be inspected
directly:

    $ cat course-data.json | jq .updates

Or you can test the public endpoint at
`/api/v2/courses-since/<timestamp>`, using timestamps from either the
raw update data and/or the initial timestamp located at the
`initial_timestamp` key in `course-data.json`.

The raw course data can be retrieved as JSON from the production
server using the undocumented and unsupported
`/experimental/course-data` endpoint.

[chromedriver]: http://chromedriver.chromium.org/
[frontend]: https://github.com/MuddCreates/hyperschedule
[jq]: https://stedolan.github.io/jq/
[httpie]: https://httpie.org/
[hyperschedule.io]: https://hyperschedule.io/
[pipenv]: https://docs.pipenv.org/
[portal]: https://portal.hmc.edu/ICS/Portal_Homepage.jnz?portlet=Course_Schedules&screen=Advanced+Course+Search&screenType=next
[python]: https://www.python.org/
[watchexec]: https://github.com/mattgreen/watchexec
