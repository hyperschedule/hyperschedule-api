"""
Module that verifies users with the front end authentication tokens 
and FireBase Admin SDK
"""

import firebase_admin
from firebase_admin import auth, credentials, firestore, storage
import os
from uuid import uuid4

# Initialize firebase
cred = credentials.Certificate(os.environ.get("FIREBASE_CREDENTIALS_PATH"))
firebase_admin.initialize_app(cred)

class APIError(Exception):
    """
    Exception that is turned into an error response from the API.
    """

    pass

def verify_token(token):
    """
    Verify user token from frontend and confirm that is a 5C email
    """
    if not token:
        raise APIError("Request failed to provide token")
        return False
    user = firebase_admin.auth.verify_id_token(token)
    # Determine if email is 5C
    suffixList = ["hmc.edu","scrippscollege.edu","pitzer.edu","pomona.edu","cmc.edu"]
    if True in list(map(user["email"].endswith,suffixList)):
        return True
    else:
        raise APIError("Invalid email suffix: ".user["email"])
        return False
    return False

def process_upload_syllabus(token, syllabus_info, pdf):
    """
    Upload the syllabus to database and store it.
    """
    if verify_token(token) == True:

        # Access token so that the file can be opened from web
        new_token = uuid4()
        metadata = {"firebaseStorageDownloadTokens": new_token, 'semester': syllabus_info[1]}

        storageBucket = storage.bucket('hyperschedule-course-info.appspot.com')
        fileBlob = storageBucket.blob("/"+syllabus_info[0])
        fileBlob.metadata = metadata
        fileBlob.upload_from_file(pdf, content_type='application/pdf')


    raise NotImplementedError("Upload Syllabus feature not implemented")
    