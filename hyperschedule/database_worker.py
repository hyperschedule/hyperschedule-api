"""
Module that verifies users with the front end authentication tokens
and FireBase Admin SDK
"""

import firebase_admin
from firebase_admin import credentials, storage, auth
import os

# Initialize firebase
cred = credentials.Certificate(os.environ.get("FIREBASE_CREDENTIALS_PATH"))
firebase_admin.initialize_app(cred, {'projectId': 'hyperschedule-course-info'})

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
    fileBlob = storageBucket.blob("courseSyllabi/" + course_code)
    fileBlob.metadata = {"semester": syllabus_date, "courseCode": course_code}
    try:
        fileBlob.upload_from_file(pdf, content_type='application/pdf')
        fileBlob.make_public()
        link = fileBlob.public_url
        update_syllabus_links(course_code, link, syllabus_date)
    except Exception as e:
        raise StorageError from e

    return True

# TODO: move this to its appropriate location
import hyperschedule.scrapers.claremont as scraper
# a dictionary from key -> course code
links = {}
semesters = {}

def update_syllabus_links_from_cloud_storage():
    storageBucket = storage.bucket('hyperschedule-course-info.appspot.com')
    blobs = list(storageBucket.list_blobs())
    for blob in blobs:
        if "courseCode" in blob.metadata:
            links[blob.metadata["courseCode"]] = blob.public_url
            semesters[blob.metadata["courseCode"]] = blob.metadata["semester"]

update_syllabus_links_from_cloud_storage()

# Update syllabus link for the given course
def update_syllabus_links(course_code, link):#,semester):
    # update
    links[course_code] = link
    semesters[course_code] = semester
    print("links updated:", links)

# Add syllabus link to the full json
def merge_links_with_json_data(data):
    # updates data to include syllabus links
    for course_code in links:
        if course_code in data["courses"]:
            data["courses"][course_code]["syllabus_link"] = links[course_code]
            data["courses"][course_code]["syllabus_term"] = semesters[course_code]
