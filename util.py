"""
Utility module shared by libcourse, libportal, and server.
"""

class ScrapeError(Exception):
    """
    Exception indicating something went wrong with webscraping.
    """

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
