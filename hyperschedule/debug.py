#!/usr/bin/env python

import json
import os
import sys

import hyperschedule.libcourse as libcourse
import hyperschedule.liblingk as liblingk
from hyperschedule.util import die

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd, = args
    key = os.environ.get("HYPERSCHEDULE_LINGK_KEY")
    secret = os.environ.get("HYPERSCHEDULE_LINGK_SECRET")
    if cmd == "write-desc-index":
        index = liblingk.get_lingk_course_description_index(key, secret, {
            "semester": libcourse.SPRING,
            "year": 2019,
        })
        with open("out/debug-desc-index.json", "w") as f:
            json.dump(index, f, indent=2)
    elif cmd == "write-lingk-data":
        data = liblingk.get_lingk_data(key, secret)
        with open("out/debug-lingk-data.json", "w") as f:
            json.dump(data, f, indent=2)
    else:
        die("invalid command: {}".format(cmd))
