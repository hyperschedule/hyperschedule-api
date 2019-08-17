"""
Module containing assorted utility functions and constants.
"""

import datetime
import os
import sys

class UnsetClass:
    """
    Singleton class used to implement `Unset`.
    """

    def __repr__(self):
        return "<Unset>"

Unset = UnsetClass()

del UnsetClass

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

def warn(message):
    """
    Log a warning to stderr with the current timestamp.
    """
    log(message)

def die(message):
    """
    Log a message to stderr with the current timestamp, and then exit
    the process reporting failure.
    """
    log("fatal: " + message)
    sys.exit(1)

# Default values for config vars. Set as cache=yes command-line
# argument or HYPERSCHEDULE_CACHE=yes environment variable.
ENV_DEFAULTS = {
    "cache": "yes",
    "debug": "yes",
    "expose": "no",
    "headless": "yes",
    "kill_orphans": "no",
    "lingk": "no",
    "port": "3000",
    "s3_read": "no",
    "s3_write": "no",
    "scraper_timeout": "120",
    "snitch": "no",
    "verbose": "yes",
}

def get_env(var):
    """
    Given the name of a config var, return its value.
    """
    env_var = "HYPERSCHEDULE_" + var.upper()
    return os.environ[env_var]

def get_env_boolean(var):
    """
    Given the name of a config var, check the envrionment and return a
    boolean. The var must be set to something that clearly indicates a
    boolean value (several formats are accepted), otherwise die.
    """
    env_var = "HYPERSCHEDULE_" + var.upper()
    val = os.environ[env_var]
    yes = (val in ("1", "on")
           or any(word.startswith(val.lower())
                  for word in ("yes", "true", "enabled")))
    if yes:
        return True
    no = (val in ("0", "off")
          or any(word.startswith(val.lower())
                 for word in ("no", "false", "disabled")))
    if no:
        return False
    die("value for boolean config var {} (= {}) is malformed: {}"
        .format(repr(var), env_var, repr(val)))

def log_verbose(message):
    """
    Log a message to stderr, but only if the 'verbose' config var is
    enabled.
    """
    if get_env_boolean("verbose"):
        log(message)
