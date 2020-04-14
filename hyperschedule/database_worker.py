"""
Module that verifies users with the front end authentication tokens
and FireBase Admin SDK
"""

import firebase_admin
from firebase_admin import auth, credentials, firestore, storage
import os

# Initialize firebase
cred = credentials.Certificate(os.environ.get("FIREBASE_CREDENTIALS_PATH"))
firebase_admin.initialize_app(cred)

class AuthError(Exception):
    pass

class StorageError(Exception):
    pass

class FirestoreError(Exception):
    pass

def is_5C_user(token):
    """
    Verifies whether the user corresponding to the token has a 5Cs email
    """
    user = firebase_admin.auth.verify_id_token(token)
    suffixes = ["@g.hmc.edu", "@hmc.edu", "@scrippscollege.edu", "@pitzer.edu", "@pomona.edu", "@cmc.edu"]
    for suffix in suffixes:
        if user["email"].endswith(suffix):
            return True
    return False

def upload_to_cloud_storage(token, course_code, syllabus_date, pdf):
    """
    Upload the syllabus to database and store it.
    """
    if not is_5C_user(token):
        raise AuthError("user is not a 5C student")

    # Upload syllabus to Firebase Storage
    storageBucket = storage.bucket('hyperschedule-course-info.appspot.com')
    fileBlob = storageBucket.blob("/courseSyllabi/" + course_code)
    fileBlob.metadata = {"semester": syllabus_date}
    try:
        fileBlob.upload_from_file(pdf, content_type='application/pdf')
    except Exception as e:
        raise StorageError from e

    return True
