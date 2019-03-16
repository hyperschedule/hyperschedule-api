class ScrapeError(Exception):
    pass

NO_DEFAULT = object()

# Modified from <https://stackoverflow.com/a/31347222/3538165>
def add_boolean_arg(parser, name, default=NO_DEFAULT, yes_args=None, no_args=None):
    group = parser.add_mutually_exclusive_group(required=default is NO_DEFAULT)
    if yes_args is None:
        yes_args = ["--" + name]
    if no_args is None:
        no_args = ["--no-" + name]
    for yes_arg in yes_args:
        group.add_argument(yes_arg, dest=name, action="store_true")
    for no_arg in no_args:
        group.add_argument(no_arg, dest=name, action="store_false")
    if default is not NO_DEFAULT:
        parser.set_defaults(**{name:default})
