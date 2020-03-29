"""
Module that verifies users with the front end authentication tokens 
and FireBase Admin SDK
"""

import hyperschedule

import firebase_admin
from firebase_admin import auth
from firebase_admin import credentials
import os


cred = credentials.Certificate(os.environ.get("FIREBASE_CREDENTIALS_PATH"))
firebase_admin.initialize_app(cred)

def verify_token():
    """
    Verify token from frontend and confirm that is a 5C email
    """
    token = flask.request.json.get("token")
    if not token:
        raise APIError("request failed to provide token")
    user = firebase_admin.auth.verify_id_token(token)
    print(user)

