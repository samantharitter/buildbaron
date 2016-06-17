import json
import urllib
import re

def get_failed_tasks(url):
    json_versions = json.loads(urllib.urlopen(url).read())
    
    for version in json_versions['versions']:
        #last_version = json_versions['versions']
        builds = version['builds']
        failed_tasks = []
        for build in builds:
            #print "Build: " + build
            name = builds[build]['name']
            for task_key in builds[build]['tasks'].keys():
                task = builds[build]['tasks'][task_key]
                if task['status'] == "failed":
                    failed_task = {"name": name, "task_id": task['task_id']}
                    failed_tasks.append(failed_task)
                    return failed_tasks

    return failed_tasks


def get_failed_tests(url):
    tasks_url = "https://evergreen.mongodb.com/rest/v1/tasks/"+failed_task['task_id']
    json_tasks = json.loads(urllib.urlopen(tasks_url).read())
    failed_tests = []
    for test, result in json_tasks['test_results'].items():
        if result['status'] != "pass":
            log_url = result['logs']['url']+'?raw=1'
            failed_tests.append({"test": test, "status": result['status'], "log_url": log_url})

    return failed_tests


def process_log(url):
    log_file = urllib.urlopen(url).read().splitlines()
    # An empty log_file might be due to a resmoke.py hook failure, i.e., #dbhash#
    # For now we will ignore it

    open_line = False
    close_line = False
    open_type = ""
    regex = re.compile(".*")
    for line in log_file:

        # Backtrace errors
        if not open_line and re.match(".*BEGIN BACKTRACE.*", line):
            open_line = True
            open_type = "backtrace"
            regex = re.compile("^.*"+line.split()[0])
        elif open_type == "backtrace" and regex.match(line) and re.match(".*END BACKTRACE.*", line):
            close_line = True

        # Leak errors
        if not open_line and re.match(".*LeakSanitizer.*", line):
            open_line = True
            open_type = "leak"
            regex = re.compile("^.*"+line.split()[0])
        elif open_type == "leak" and regex.match(line) and re.match(".*SUMMARY: AddressSanitizer.*", line):
            close_line = True

        # Asserts
        if not open_line and re.match(".*assert:.*", line):
            open_line = True
            open_type = "assert"
            regex = re.compile("^.*"+line.split()[0])
        elif open_type == "assert" and regex.match(line) and re.match(".* $", line):
            close_line = True

        if open_line and regex.match(line):
            print(line)
        if close_line:
            open_line = False
            close_line = False
            open_type = ""
            regex = re.compile(".*")


versions_url = "https://evergreen.mongodb.com/rest/v1/projects/mongodb-mongo-master/versions"

for failed_task in get_failed_tasks(versions_url):
    print failed_task
    tasks_url = "https://evergreen.mongodb.com/rest/v1/tasks/"+failed_task['task_id']
    for failed_test in get_failed_tests(tasks_url):
        print(" ")
        print(failed_task['name'], failed_test)
        #process_log(failed_test['log_url'])
