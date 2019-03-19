"""
Utility module shared by libcourse, libportal, and server.
"""

import datetime
import sys

class ScrapeError(Exception):
    """
    Exception indicating something went wrong with webscraping.
    """

def format_timestamp():
    """
    Return a string representing the current date and time.
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(message):
    """
    Log a message to stderr with the current timestamp.
    """
    print("[{}] {}".format(format_timestamp(), message), file=sys.stderr)

def die(message):
    """
    Log a message to stderr with the current timestamp, and then exit
    the process reporting failure.
    """
    log("fatal: " + message)
    sys.exit(1)

NO_DEFAULT = object()

# Modified from <https://stackoverflow.com/a/31347222/3538165>
def add_boolean_arg(
        parser, name, default=NO_DEFAULT, yes_args=None, no_args=None):
    """
    Add a boolean argument to the given argparse parser. By default
    the --name and --no-name flags are generated, storing True and
    False respectively into name, and it is mandatory to specify one
    of the flags. If default is provided, then specifying a flag is no
    longer mandatory. You can override --name with a list of synonyms
    by passing yes_args, and likewise for --no-name with no_args.
    """
    dest = name.replace("-", "_")
    group = parser.add_mutually_exclusive_group(required=default is NO_DEFAULT)
    if yes_args is None:
        yes_args = ["--" + name]
    if no_args is None:
        no_args = ["--no-" + name]
    for yes_arg in yes_args:
        group.add_argument(yes_arg, dest=dest, action="store_true")
    for no_arg in no_args:
        group.add_argument(no_arg, dest=dest, action="store_false")
    if default is not NO_DEFAULT:
        parser.set_defaults(**{dest: default})
