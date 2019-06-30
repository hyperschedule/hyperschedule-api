"""
Module that runs the Flask app in either development or production
mode, after setting up environment variables appropriately.
"""

import argparse
import os
import shlex
import subprocess
import sys

import hyperschedule.util as util

def exec_cmd(cmd):
    """
    Print a shell command (a list) and run it.
    """
    print(" ".join(map(shlex.quote, cmd)))
    try:
        sys.exit(subprocess.run(cmd).returncode)
    except KeyboardInterrupt:
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hyperschedule backend server")
    parser.add_argument("config", metavar="key=val", nargs="*",
                        help="config var settings (see README)")
    config_args = parser.parse_args().config
    config = {}
    for config_arg in config_args:
        if "=" not in config_arg:
            util.die("malformed key=val argument: {}".format(repr(config_arg)))
        var, val = config_arg.split("=", maxsplit=1)
        if var not in util.ENV_DEFAULTS:
            util.die("unknown config var: {}".format(repr(var)))
        config[var] = val
    for var, val in util.ENV_DEFAULTS.items():
        if var not in config:
            config[var] = val
        val = config[var]
        env_var = "HYPERSCHEDULE_" + var.upper()
        os.environ[env_var] = val
    app = "hyperschedule.api.app:app"
    port = util.get_env("port")
    host = "0.0.0.0" if util.get_env_boolean("expose") else "127.0.0.1"
    if util.get_env_boolean("debug"):
        os.environ["FLASK_ENV"] = "development"
        os.environ["FLASK_APP"] = app
        os.environ["FLASK_SKIP_DOTENV"] = "1"
        exec_cmd(["flask", "run",
                  "--host", host,
                  "--port", port,
                  "--no-reload"])
    else:
        exec_cmd(["gunicorn", "-w", "1", "-b",
                  "{}:{}" .format(host, port), app])
