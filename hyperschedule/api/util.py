"""
Module containing shared utility code for the API server.
"""

from hyperschedule.util import Unset

class UserError(Exception):
    """
    Exception raised when the user does something wrong in their API
    request.
    """

    def __init__(self, message, code=Unset, *args, **kwargs):
        super().__init__(message, *args, **kwargs)
        self.code = code

class InternalError(Exception):
    """
    Exception raised when we mess up.
    """
