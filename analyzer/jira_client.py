"""
Jira Client and utility operations
"""
import argparse
import getpass
import json
import os
import pprint
import re
import threading

from jira import JIRA

try:
    import keyring
except ImportError:
    keyring = None


class jira_client(object):
    """Simple wrapper around jira api for build baron analyzer needs"""

    def __init__(self, jira_server, jira_user):

        self.jira = JIRA(
            options={'server': jira_server,
                     'verify': False},
            basic_auth=(jira_user, jira_client._get_password(jira_server, jira_user)),
            validate=True)

        # Since the web server may share this client among threads, use a lock since it unclear if the JIRA client is thread-safe
        self._lock = threading.Lock()

    @staticmethod
    def _get_password(server, user):
        global keyring

        password = None

        if keyring:
            try:
                password = keyring.get_password(server, user)
            except:
                print("Failed to get password from keyring")
                keyring = None

        if password is not None:
            print("Using password from system keyring.")
        else:
            password = getpass.getpass("Jira Password:")

            if keyring:
                answer = input("Store password in system keyring? (y/N): ").strip()

                if answer == "y":
                    keyring.set_password(server, user, password)

        return password

    def query_duplicates_text(self, fields):
        search = "project in (bf, server, evg, build) AND (" + " or ".join(
            ['text~"%s"' % f for f in fields]) + ") ORDER BY updated DESC"
        return search

    def search_issues(self, query, maxResults=50):
        with self._lock:
            results = self.jira.search_issues(
                query,
                fields=[
                    "id", "key", "status", "resolution", "summary", "created", "updated",
                    "assignee", "description"
                ],
                maxResults=maxResults)

        print("Found %d results" % len(results))

        return results

# jira.resolutions()
#[<JIRA Resolution: name='Fixed', id='1'>,
# <JIRA Resolution: name="Won't Fix", id='2'>,
# <JIRA Resolution: name='Duplicate', id='3'>,
# <JIRA Resolution: name='Incomplete', id='4'>,
# <JIRA Resolution: name='Cannot Reproduce', id='5'>,
# <JIRA Resolution: name='Works as Designed', id='6'>,
# <JIRA Resolution: name='Gone away', id='7'>,
# <JIRA Resolution: name='Community Answered', id='8'>,
# <JIRA Resolution: name='Done', id='9'>]

# Issue link Types
#[<JIRA IssueLinkType: name='Backports', id='10420'>,
# <JIRA IssueLinkType: name='Depends', id='10011'>,
# <JIRA IssueLinkType: name='Documented', id='10320'>,
# <JIRA IssueLinkType: name='Duplicate', id='10010'>,
# <JIRA IssueLinkType: name='Gantt Dependency', id='10020'>,
# <JIRA IssueLinkType: name='Gantt End to End', id='10423'>,
# <JIRA IssueLinkType: name='Gantt End to Start', id='10421'>,
# <JIRA IssueLinkType: name='Gantt Start to End', id='10424'>,
# <JIRA IssueLinkType: name='Gantt Start to Start', id='10422'>,
# <JIRA IssueLinkType: name='Related', id='10012'>,
# <JIRA IssueLinkType: name='Tested', id='10220'>]

    def close_as_duplicate(self, issue, duplicate_issue):

        with self._lock:
            src_issue = self.jira.issue(issue)
            dest_issue = self.jira.issue(duplicate_issue)

            # Add duplicate link
            self.jira.create_issue_link(
                type='Duplicate', inwardIssue=issue, outwardIssue=duplicate_issue)

            # Close - id 2
            # Duplicate issue is 3
            self.jira.transition_issue(src_issue, '2', resolution={'id': '3'})

    def close_as_goneaway(self, issue):
        with self._lock:
            src_issue = self.jira.issue(issue)

            # Close - id 2
            # Gone away is 7
            self.jira.transition_issue(
                src_issue, '2', comment="Transient machine issue.", resolution={'id': '7'})
