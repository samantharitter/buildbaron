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
import threading

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__))))))
print(sys.path)

lib_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__)))))
print(lib_path)

import analyzer.jira_client
import analyzer.analyzer_config


@app.route('/')
@app.route('/home')
def home():
    """Renders the home page."""

    with open(os.path.join(lib_path, "failed_bfs.json"), "rb") as sjh:
        contents = sjh.read().decode('utf-8')
        failed_bfs = json.loads(contents)

    return render_template(
        'index.html',
        title='Home Page',
        year=datetime.now().year
        #,failed_tests=g.get("failed_tests", None)
        ,
        failed_bfs=failed_bfs,
        bf_count=len(failed_bfs))


statusKeys = {
    "Blocked": 1,
    "Open": 1,
    "In Progress": 1,
    'Waiting for bug fix': 1,
    'Waiting For User Input': 1,
    'In Code Review': 1,
    "Needs Scope": 1,
    "Requested": 1,
    'Stuck': 1,
    "Closed": 2,
    "Resolved": 2,
    "Completed": 2,
}


def issue_sort(issue):

    k1 = statusKeys[issue.fields.status.name]

    if (k1 == 2):
        if issue.fields.resolution is not None and issue.fields.resolution.name == "Fixed":
            k2 = 0
        else:
            k2 = 1
    else:
        k2 = 3

    return "%d_%d" % (k1, k2)


jira_client_cached = None
jira_client_lock = threading.Lock()


def get_jira_client():
    global jira_client_cached
    global jira_client_lock

    with jira_client_lock:
        if jira_client_cached is None:
            print("Connecting to JIRA.....")
            jira_client_cached = analyzer.jira_client.jira_client(
                analyzer.analyzer_config.jira_server(), analyzer.analyzer_config.jira_user())
        return jira_client_cached


@app.route('/failure')
def failure():
    """Renders the failure page."""
    with open(os.path.join(lib_path, "failed_bfs.json"), "rb") as sjh:
        contents = sjh.read().decode('utf-8')
        failed_bfs = json.loads(contents)
    global ja

    issue = request.args.get('issue')
    test_name = request.args.get('test_name')

    failed_bf = None

    for ft in failed_bfs:
        if ft["test"]["issue"] == issue and test_name == ft["test"]["name"]:
            failed_bf = ft

    # Predicates
    jc = get_jira_client()
    jira_query = jc.query_duplicates_text([os.path.basename(test_name), failed_bf['test']['suite']])
    issues = jc.search_issues(jira_query)

    issues.sort(key=issue_sort)

    is_system_failure = "System Failure" in failed_bf['test']['summary']

    # Query for the last few issues the user has looked at
    recent_issues_query = "issuekey in issueHistory() and project in (bf, server, evg, build) ORDER BY lastViewed DESC"
    recent_issues = jc.search_issues(recent_issues_query)

    recent_issues.sort(key=issue_sort)

    return render_template(
        'failure.html',
        title='Failure Details',
        year=datetime.now().year,
        failed_bf=failed_bf,
        issues=issues,
        jira_query=jira_query,
        recent_issues=recent_issues,
        recent_issues_query=recent_issues_query,
        is_system_failure=is_system_failure)


@app.route('/resolve_duplicate')
def resolve_duplicate():
    """Renders the duplicate page."""

    issue = request.args.get('issue')
    duplicate_issue = request.args.get('duplicate_issue')

    jc = get_jira_client()

    jc.resolve_as_duplicate(issue, duplicate_issue)

    return render_template(
        'duplicate.html',
        title='Ticket Resolved',
        year=datetime.now().year,
        issue=issue,
        duplicate_issue=duplicate_issue)


@app.route('/resolve_goneaway')
def resolve_goneaway():
    """Renders the gone away page."""

    issue = request.args.get('issue')

    jc = get_jira_client()
    jc.resolve_as_goneaway(issue)

    return render_template(
        'gone_away.html', title='Ticket Resolved', year=datetime.now().year, issue=issue)


@app.route('/about')
def about():
    """Renders the about page."""
    return render_template(
        'about.html',
        title='About',
        year=datetime.now().year,
        message='Third Party License Notices')
