#!/usr/bin/env python3

import argparse
import json
import libportal
import sys

import util

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    util.add_boolean_arg(parser, "headless")
    util.add_boolean_arg(parser, "kill-chrome")
    args = parser.parse_args()
    json.dump(libportal.get_latest_course_list({
        "headless": args.headless,
        "kill_chrome": args.kill_chrome,
    }), sys.stdout)
