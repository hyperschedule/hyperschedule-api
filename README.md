**Hyperschedule Scraper**: retrieving course data from the worst
database ever.

## See also

Hyperschedule has three services: the [front-end webapp][webapp], the
[course catalog API][api], and the Portal scraper (this repository).

Currently, the course catalog and the Portal scraper are still one
service. They will be separated once the [new API][new-api] is up and
running.

## Local development
### Install dependencies
#### macOS

Install [Homebrew]:

    $ /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

Install [Yarn]:

    $ brew install yarn

Install [Python 3][python]:

    $ brew install python3

### Set up project

Install Node.js dependencies:

    $ yarn

Create a virtual environment:

    $ python3 -m venv venv

Enter the virtual environment:

    $ source venv/bin/activate

Install Python dependencies:

    $ pip install -r requirements.txt

### Run locally

Run the scraper and serve the API on `localhost:3000` (use a different
port by exporting `PORT`):

    $ yarn server

Run in production mode (increases exponential backoff):

    $ yarn server --production

### Deploy

Deployment happens automatically when a commit is merged to `master`.

[api]: https://github.com/MuddCreates/hyperschedule-scraper
[homebrew]: https://brew.sh/
[new-api]: https://github.com/MuddCreates/hyperschedule-api
[python]: https://www.python.org/
[webapp]: https://github.com/MuddCreates/hyperschedule
[yarn]: https://yarnpkg.com/en/
