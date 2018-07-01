## Hyperschedule scraper

This repository contains a Python webapp which scrapes information
from the [Claremont Colleges course catalog][portal] and exposes it
via a faster and more usable JSON API.

This service is used as the backend for the [Hyperschedule
webapp][frontend]. Since that webapp was previously hosted on the same
domain as the API, the service in this repository also serves a single
HTML page at the domain root which directs users to copy their data
and migrate to the new frontend domain.

You may see the webapp in action by visiting the following URLs:

* https://hyperschedule.herokuapp.com/api/v1/all-courses
* https://hyperschedule.herokuapp.com/

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

Course objects are maps with the following keys:
* `courseCodeSuffix`
  * string, possibly empty
* `courseName`
  * non-empty string
* `courseNumber`
  * positive integer
* `courseStatus`
  * string, one of `open`, `closed`, or `reopened`
* `department`
  * non-empty string
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
  * list of maps, possible empty, with keys:
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
  * non-empty string
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
`courseCodeSuffix`, or `section`.

## Development

First, install the following dependencies:

* [Python 3][python]
* [Pipenv][pipenv]
* [PhantomJS][phantomjs] (to use the default headless scraper)
* [ChromeDriver][chromedriver] (to instead use the graphical scraper
  for debugging)

Then, install the Python dependencies into a virtualenv by running:

    $ pipenv install

You may start the server in development mode on `localhost:3000` by
running:

    $ pipenv run ./server.py --dev

To run in production mode instead, pass `--prod`. You can change the
port that the server listens on by exporting the environment variable
`PORT`.

If you wish to debug the web scraping, you can tell the server to use
Chrome instead of PhantomJS, so that you can see what is going on.
This is achieved by passing the argument `--no-headless`. That can be
overridden by `--headless`.

[chromedriver]: http://chromedriver.chromium.org/
[frontend]: https://github.com/MuddCreates/hyperschedule
[hyperschedule.io]: https://hyperschedule.io/
[phantomjs]: http://phantomjs.org/
[pipenv]: https://docs.pipenv.org/
[portal]: https://portal.hmc.edu/ICS/Portal_Homepage.jnz?portlet=Course_Schedules&screen=Advanced+Course+Search&screenType=next
[python]: https://www.python.org/
