"""
Routes and views for the flask application.
"""
import json

from datetime import datetime
from flask import request
from flask import render_template, g
from www import app
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__))))))
print (sys.path)

lib_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__)))))
print(lib_path)

import analyzer.jira_analyzer

@app.route('/')
@app.route('/home')
def home():
    """Renders the home page."""

    with open(os.path.join(lib_path, "failed_tests.json"), "rb") as sjh:
        contents = sjh.read().decode('utf-8')
        failed_tests = json.loads(contents)

    return render_template(
        'index.html',
        title='Home Page',
        year=datetime.now().year
        #,failed_tests=g.get("failed_tests", None)
        ,failed_tests=failed_tests
    )

statusKeys = {
    "Blocked": 1,
    "Open": 1,
    "In Progress": 1,
    "Closed": 2,
    "Resolved": 2,
}

def issue_sort(issue):

    k1 = statusKeys[issue.fields.status.name];

    if(k1 == 2):
        if issue.fields.resolution.name == "Fixed":
            k2 = 0
        else:
            k2 = 1
    else:
        k2 = 3

    return "%d_%d" % (k1, k2)

@app.route('/failure')
def failure():
    """Renders the failure page."""
    with open(os.path.join(lib_path, "failed_tests.json"), "rb") as sjh:
        contents = sjh.read().decode('utf-8')
        failed_tests = json.loads(contents)

    task_id = request.args.get('task_id')
    build_id = request.args.get('build_id')
    test_name = request.args.get('test_name')

    failed_test=None

    print (task_id)
    print (build_id)
    print (test_name)

    for ft in failed_tests:
        if ft["test"]["task_id"] == task_id and build_id == ft["test"]["task_name"] and test_name == ft["test"]["test"]:
            failed_test = ft

    ja = analyzer.jira_analyzer.jira_analyzer("https://jira.mongodb.com", os.getenv("JIRA_USER_NAME", "mark.benvenuto"))

    issues = ja.query([build_id, os.path.basename(test_name)]);

    issues.sort(key=issue_sort)

    return render_template(
        'failure.html',
        title='Failure Details',
        year=datetime.now().year
        ,failed_test=failed_test
        ,issues = issues
    )

@app.route('/contact')
def contact():
    """Renders the contact page."""
    return render_template(
        'contact.html',
        title='Contact',
        year=datetime.now().year,
        message='Your contact page.'
    )

@app.route('/about')
def about():
    """Renders the about page."""
    return render_template(
        'about.html',
        title='About',
        year=datetime.now().year,
        message='Your application description page.'
    )
