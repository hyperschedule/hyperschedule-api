#!/usr/bin/env python3

import argparse
import json
import libportal
import sys

import util

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    util.add_boolean_arg(parser, "headless")
    args = parser.parse_args()
    json.dump(libportal.get_latest_course_list(args.headless), sys.stdout)
