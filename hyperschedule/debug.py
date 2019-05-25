#!/usr/bin/env python

import json
import os
import pprint
import subprocess
import sys

import hyperschedule
import hyperschedule.scrapers.claremont as scraper
import hyperschedule.scrapers.claremont.lingk as lingk
import hyperschedule.util as util

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd, = args
    for var, val in util.ENV_DEFAULTS.items():
        env_var = "HYPERSCHEDULE_" + var.upper()
        if not os.environ.get(env_var):
            os.environ[env_var] = val
    if cmd == "run-scraper":
        fname = hyperschedule.ROOT_DIR / "out" / "run-scraper.json"
        print("Running scraper")
        course_data = scraper.get_course_data(None)
        print("Writing to file {}".format(fname))
        with open(fname, "w") as f:
            json.dump(course_data, f, indent=2)
            f.write("\n")
    elif cmd == "repl":
        try:
            sys.exit(subprocess.run(["python"]).returncode)
        except KeyboardInterrupt:
            sys.exit(1)
    elif cmd == "scrape-lingk":
        fname = hyperschedule.ROOT_DIR / "out" / "scrape-lingk.py"
        print("Scraping Lingk")
        desc_index = lingk.get_course_descriptions()
        print("Writing to file {}".format(fname))
        with open(fname, "w") as f:
            pprint.pprint(desc_index, f)
    else:
        util.die("invalid command: {}".format(cmd))
