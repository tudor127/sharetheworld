# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime
import logging
import os
import json

from flask import Flask, redirect, render_template, request, session

from google.cloud import datastore
from google.cloud import storage
from google.cloud import vision
from google.cloud.vision import types

CLOUD_STORAGE_BUCKET = os.environ.get('CLOUD_STORAGE_BUCKET')


app = Flask(__name__)


@app.route('/')
def homepage():
    # session.pop('test')

    if 'email' in session:
        # Create a Cloud Datastore client.
        datastore_client = datastore.Client()
        query = datastore_client.query(kind='users')
        query.add_filter('email', '=', session['email'])
        username = list(query.fetch())[0]['username']

        posts_query = datastore_client.query(kind='posts')
        posts = list(posts_query.fetch())

        return render_template('homepage.html',username=username,posts=posts)
    else:
        return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    session['email'] = email

    # Redirect to the home page.
    return redirect('/')


@app.route('/register', methods=['GET', 'POST'])
def register():

    email = request.form['email']
    username = request.form['username']

    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()

    # Fetch the current date / time.
    current_datetime = datetime.now()

    # The kind for the new entity.
    kind = 'users'

    # Create the Cloud Datastore key for the new entity.
    key = datastore_client.key(kind, email)

    # Construct the new entity using the key. Set dictionary values for entity
    entity = datastore.Entity(key)
    entity['email'] = email
    entity['username'] = username
    entity['registration_date'] = current_datetime

    # Save the new entity to Datastore.
    datastore_client.put(entity)

    session['email'] = email

    # Redirect to the home page.
    return redirect('/')

@app.route('/addpost', methods=['GET', 'POST'])
def addpost():

    description = request.form['description']

    photo = request.files['file']

    # Create a Cloud Storage client.
    storage_client = storage.Client()

    # Get the bucket that the file will be uploaded to.
    bucket = storage_client.get_bucket(CLOUD_STORAGE_BUCKET)

    # Create a new blob and upload the file's content.
    blob = bucket.blob(photo.filename)
    blob.upload_from_string(
            photo.read(), content_type=photo.content_type)

    # Make the blob publicly viewable.
    blob.make_public()

    # Create a Cloud Vision client.
    client = vision.ImageAnnotatorClient()

    # Use the Cloud Vision client to detect a face for our image.
    source_uri = 'gs://{}/{}'.format(CLOUD_STORAGE_BUCKET, blob.name)
    image = vision.types.Image(
        source=vision.types.ImageSource(gcs_image_uri=source_uri))

    # Performs label detection on the image file
    response = client.label_detection(image=image)

    labels = response.label_annotations

    labels_array = []

    count = 0

    for label in labels:
        labels_array.append({count:label.description})
        count+=1

    labels = json.dumps(labels_array)

    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()

    # Fetch the current date / time.
    current_datetime = datetime.now()

    # The kind for the new entity.
    kind = 'posts'

    # The name/ID for the new entity.
    name = blob.name

    # Create the Cloud Datastore key for the new entity.
    key = datastore_client.key(kind, name)

    # Construct the new entity using the key. Set dictionary values for entity
    entity = datastore.Entity(key)
    entity['image_name'] = name
    entity['image_url'] = blob.public_url
    entity['description'] = description
    entity['labels'] = labels
    entity['date_added'] = current_datetime

    # Save the new entity to Datastore.
    datastore_client.put(entity)

    # Redirect to the home page.
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear();
    # Redirect to the home page.
    return redirect('/')


@app.route('/upload_photo', methods=['GET', 'POST'])
def upload_photo():
    photo = request.files['file']

    # Create a Cloud Storage client.
    storage_client = storage.Client()

    # Get the bucket that the file will be uploaded to.
    bucket = storage_client.get_bucket(CLOUD_STORAGE_BUCKET)

    # Create a new blob and upload the file's content.
    blob = bucket.blob(photo.filename)
    blob.upload_from_string(
            photo.read(), content_type=photo.content_type)

    # Make the blob publicly viewable.
    blob.make_public()

    # Create a Cloud Vision client.
    vision_client = vision.ImageAnnotatorClient()

    # Use the Cloud Vision client to detect a face for our image.
    source_uri = 'gs://{}/{}'.format(CLOUD_STORAGE_BUCKET, blob.name)
    image = vision.types.Image(
        source=vision.types.ImageSource(gcs_image_uri=source_uri))
    faces = vision_client.face_detection(image).face_annotations

    # If a face is detected, save to Datastore the likelihood that the face
    # displays 'joy,' as determined by Google's Machine Learning algorithm.
    if len(faces) > 0:
        face = faces[0]

        # Convert the likelihood string.
        likelihoods = [
            'Unknown', 'Very Unlikely', 'Unlikely', 'Possible', 'Likely',
            'Very Likely']
        face_joy = likelihoods[face.joy_likelihood]
    else:
        face_joy = 'Unknown'

    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()

    # Fetch the current date / time.
    current_datetime = datetime.now()

    # The kind for the new entity.
    kind = 'Faces'

    # The name/ID for the new entity.
    name = blob.name

    # Create the Cloud Datastore key for the new entity.
    key = datastore_client.key(kind, name)

    # Construct the new entity using the key. Set dictionary values for entity
    # keys blob_name, storage_public_url, timestamp, and joy.
    entity = datastore.Entity(key)
    entity['blob_name'] = blob.name
    entity['image_public_url'] = blob.public_url
    entity['timestamp'] = current_datetime
    entity['joy'] = face_joy

    # Save the new entity to Datastore.
    datastore_client.put(entity)

    # Redirect to the home page.
    return redirect('/')


@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500


if __name__ == '__main__':
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.secret_key = "pass"
    app.run(host='127.0.0.1', port=8083, debug=True) 
