"""
Connects to firebase for authentication and storage.

Currently, the module is only used for 
"""

import firebase_admin
from firebase_admin import credentials, storage
import os

# Initialize firebase from FIREBASE_CREDENTIALS_PATH environment variable
credentials_path = os.environ["FIREBASE_CREDENTIALS_PATH"]
credentials = credentials.Certificate(credentials_path)
firebase_admin.initialize_app(credentials, {'projectId': 'hyperschedule-course-info'})

BUCKET_NAME = 'hyperschedule-course-info.appspot.com'
STORAGE_PATH = "courseSyllabi/"

# dictionary from course code to link
syllabus_info = {}

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
    try:
        user = firebase_admin.auth.verify_id_token(token)
    except Exception as e:
        raise AuthError from e
    suffixes = ["@g.hmc.edu", "@hmc.edu", "@scrippscollege.edu", "@pitzer.edu", "@pomona.edu", "@cmc.edu"]
    for suffix in suffixes:
        if user["email"].endswith(suffix):
            return True
    return False

def upload_to_cloud_storage(token, course_code, syllabus_date, pdf):
    """
    Upload the syllabus to database and update the information in syllabus_info.
    """
    if not is_5C_user(token):
        raise AuthError("user is not a 5C student")

    # Upload syllabus to Firebase Storage
    storageBucket = storage.bucket(BUCKET_NAME)
    fileBlob = storageBucket.blob(STORAGE_PATH + course_code)
    fileBlob.metadata = {"semester": syllabus_date, "courseCode": course_code}
    try:
        fileBlob.upload_from_file(pdf, content_type='application/pdf')
        fileBlob.make_public()
        link = fileBlob.public_url
        update_syllabus_info(course_code, {"link": link, "semester": syllabus_date})
    except Exception as e:
        raise StorageError from e
    return True

def initialize_syllabus_info_from_cloud_storage():
    try:
        storageBucket = storage.bucket(BUCKET_NAME)
        blobs = list(storageBucket.list_blobs())
    except Exception as e:
        raise StorageError from e
    for blob in blobs:
        if "courseCode" in blob.metadata:
             info = {"link": blob.public_url, "semester": blob.metadata["semester"]}
             syllabus_info[blob.metadata["courseCode"]] = info

def update_syllabus_info(course_code, info):
    """
    Update local syllabus information of a course.
    """
    syllabus_info[course_code] = info

def merge_syllabus_info_to_courses(data):
    """
    Merge syllabus information to course data. This adds a new key "syllabus_link" to each
    course in data.
    """
    for course_code in syllabus_info:
        if course_code in data["courses"]:
            data["courses"][course_code]["syllabus"] = syllabus_info[course_code]

initialize_syllabus_info_from_cloud_storage()
