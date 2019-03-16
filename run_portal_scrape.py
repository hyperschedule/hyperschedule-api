#!/usr/bin/env python3

import argparse
import json
import libportal
import sys

# Modified from <https://stackoverflow.com/a/31347222/3538165>
def add_boolean_arg(parser, name, default=None):
    group = parser.add_mutually_exclusive_group(required=default is None)
    group.add_argument("--"    + name, dest=name, action="store_true" )
    group.add_argument("--no-" + name, dest=name, action="store_false")
    if default is not None:
        parser.set_defaults(**{name:default})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_boolean_arg(parser, "headless")
    args = parser.parse_args()
    json.dump(libportal.get_latest_course_list(args.headless), sys.stdout)
