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
#firebase_admin.initialize_app(cred)

def verify_token():
    """
    Verify user token from frontend and confirm that is a 5C email
    """
    token = flask.request.json.get("token")
    if not token:
        raise APIError("request failed to provide token")
    user = firebase_admin.auth.verify_id_token(token)
    
    # Determine if email is 5C
    suffixList = ["hmc.edu","scrippscollege.edu","pitzer.edu","pomona.edu"]
    if True in list(map(user["email"].endswith,suffixList)):
        raise NotImplementedError("Email checking not fully implemented")
    

