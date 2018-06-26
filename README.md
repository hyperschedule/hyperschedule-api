**Hyperschedule scraper**: retrieving course data from the worst
database ever.

## Live demo

Checkout https://hyperschedule.herokuapp.com/api/v1/all-courses!

## See also

This repository contains only the backend web service for
Hyperschedule, which scrapes information from the Claremont Colleges
course catalog and serves a single JSON endpoint as well as an index
HTML page that redirects people to the frontend webapp (since the
frontend webapp was *previously* hosted on the same domain as the
API). The code for the frontend webapp is located [here][webapp].

## Local development

Install [Yarn] and [Python 3][python]. It is considered best practice
to create a virtualenv for the Python dependencies.

Install the NPM dependencies by running `yarn` in the project root,
and install the Python dependencies by running `pip3 install -r
requirements.txt`. You are ready to run the backend server locally:

    $ yarn server

This serves the API (and index HTML page) on `localhost:3000`; you may
substitute a different port by exporting `PORT`. You can test the API
by requesting `localhost:3000/api/v1/all-courses`, and the index HTML
page by visiting `localhost:3000`.

To run the server in production mode, which increases the exponential
backoff against the course catalog database, you can pass the
`--production` option to `yarn server`.

### Deploy

Deployment to Heroku happens automatically when a commit is merged to
`master`. If you have permission to manage the deployment pipeline,
the administrator dashboard is [here][heroku].

[heroku]: https://dashboard.heroku.com/apps/hyperschedule
[python]: https://www.python.org/
[webapp]: https://github.com/MuddCreates/hyperschedule
[yarn]: https://yarnpkg.com/en/
