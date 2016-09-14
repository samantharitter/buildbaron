import json
import urllib.request
import re
import os
import sys
import hashlib
import binascii
import pprint
import argparse
import stat
import concurrent.futures
from multiprocessing import cpu_count

#if __name__ == "__main__" and __package__ is None:
#    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__)))))

from . import log_file_analyzer

def get_url(url):
    with urllib.request.urlopen(url) as f:
        s1 = f.read().decode('utf-8')
    return s1

def get_failed_tasks(url):
    """Iterate through all versions and get a list of failed tasks"""
    print("Grabbing failed tasks: " + url)
    json_versions = json.loads(get_url(url))
    failed_tasks = []
    
    i = 0
    print ("Checking %d versions" % (len(json_versions['versions'])))
    for version in json_versions['versions']:
        #last_version = json_versions['versions']
        builds = version['builds']
        for build in builds:
            #print("Build: " + build)
            name = builds[build]['name']
            for task_key in builds[build]['tasks'].keys():
                task = builds[build]['tasks'][task_key]
                if task['status'] == "failed":
                    failed_task = {"name": name, "task_id": task['task_id']}
                    failed_tasks.append(failed_task)
                    i = i + 1
                    #if i > 3:
                    #    return failed_tasks

    return failed_tasks


def get_failed_tests(failed_task):
    """Iterate through each failed task, and grab each test that failed"""
    tasks_url = "https://evergreen.mongodb.com/rest/v1/tasks/"+failed_task['task_id']
    json_tasks = json.loads(get_url(tasks_url))
    failed_tests = []

    task_id = json_tasks["id"]
    build_variant = json_tasks["build_variant"] #windows, linux, etc
    task_name = json_tasks["display_name"] # like unittests, compile, etc    
    task_time_taken = json_tasks["time_taken"]
    finish_time = json_tasks["finish_time"]

    i = 0
    for test, result in json_tasks['test_results'].items():
        if result['status'] != "pass":
            log_url = result['logs']['url']+'?raw=1'
            failed_tests.append({"test": test, "status": result['status'], "log_url": log_url, 
                                 "task_id" : task_id, "build_variant" : build_variant, "task_name" : task_name,
                                 "finish_time" : finish_time})

            # Never grab more than 10 tests in a failed task otherwise things are badly broken
            i = i + 1
            if i == 10:
                print("Exceeding test failure threshold for task: %s" % tasks_url)
                break;

    return failed_tests


def process_log_cached(failed_test):
    """Create a directory to cache the log file in"""
    if not os.path.exists("cache"):
        os.mkdir("cache");

    m = hashlib.sha1()
    m.update(failed_test["task_name"].encode())
    m.update(failed_test["task_id"].encode())
    m.update(failed_test["test"].encode())
    digest = m.digest()
    digest64 = binascii.b2a_hex(digest).decode()
    failed_test["hash"] = digest64
    path = os.path.join("cache", digest64)
    failed_test["cache"] = path

    if not os.path.exists(path):
        os.mkdir(path)
    
    return process_log(failed_test);


def process_log(failed_test):
    """Process a log through the log file analyzer

    Saves test information in cache\XXX\test.json
    Saves analysis information in cache\XXX\summary.json
    """
    pp = pprint.PrettyPrinter()
    print("Test: " + str(failed_test))

    if "jumbo" in failed_test["test"]:
        return None
    
    cache_dir = failed_test["cache"]
    log_file = os.path.join(cache_dir, "test.log")

    if not os.path.exists(log_file):
        if failed_test["log_url"].startswith("?"): # jepsen failures
            with open(log_file, "w") as th:
                th.write("Jepsen analysis not supported by log_file_analyzer.py\n")
        else:
            print("Downloading file")
            urllib.request.urlretrieve(failed_test["log_url"], log_file)

    #test_json = os.path.join(cache_dir, "test.json")
    summary_json = os.path.join(cache_dir, "summary.json")

    log_file_stat = os.stat(log_file)

    if log_file_stat[stat.ST_SIZE] > 10 * 1024 * 1024:
        summary_str = "Skipping Large File : " + str(log_file_stat[stat.ST_SIZE] )
        return { "test" : failed_test, "summary" : summary_str  }

    if os.path.exists(summary_json):
        with open(summary_json, "rb") as sjh:
            contents = sjh.read().decode('utf-8')
            summary_str = json.loads(contents)

        return { "test" : failed_test, "summary" : summary_str  }

    # check for log files > 10MB??
    if log_file_stat[stat.ST_SIZE] > 10 * 1024 * 1024:
        summary_str = "Skipping Large File : " + str(log_file_stat[stat.ST_SIZE] )
        print(summary_str)
        summary_obj = summary_str
    else:
        with open(log_file, "rb") as lfh:
            log_file_str = lfh.read().decode('utf-8')
    
        print("Checking Log File")
        LFS = log_file_analyzer.LogFileSplitter(log_file_str)

        s = LFS.getsplits()
    
        analyzer = log_file_analyzer.LogFileAnalyzer(s)

        analyzer.analyze()

        faults = analyzer.get_faults()

        if len(faults) == 0:
            print("===========================")
            print("Analysis failed for test: " + pp.pformat(failed_test))
            print("To Debug: python analyzer\\log_file_analyzer.py %s " % (log_file))
            print("===========================")

        for f in analyzer.get_faults():
            print(f)

        summary_str = analyzer.to_json()
        summary_obj = json.loads(summary_str)

    with open(summary_json, "wb") as sjh:
        sjh.write(summary_str.encode())


    #with open(test_json, "wb") as tjh:
    #    json.dump(failed_test, tjh);

    return { "test" : failed_test, "summary" : summary_obj }

versions_url = "https://evergreen.mongodb.com/rest/v1/projects/mongodb-mongo-master/versions"

def get_failed_test_info(base_url):
    """Analyzes all failures"""
    faild_tests = []
    i = 0

    # TODO- parallelize this loop
    for failed2_task in get_failed_tasks(versions_url):
        print(failed2_task)
        faild_tests += get_failed_tests(failed2_task)
        i = i + 1
        #if i > 5:
        #    break

    print("Analyzing %d tests" % (len(faild_tests)))

    results = []
    for failed2_test in faild_tests:
        print(" ")
        #print(failed2_task['name'], failed2_test)
        #process_log(failed_test['log_url'])
        analysis = process_log_cached(failed2_test)
        if analysis:
            results.append(analysis)
        #i = i + 1
        #if i > 5:
        #    break

    return results


def get_builds(base_url, commit):
    """get a list of build ids
     """
    url = base_url + "/rest/v1/projects/mongodb-mongo-master/revisions/" + commit

    json_revision = json.loads(get_url(url))

    return json_revision["builds"]

def get_failed_tasks_from_buildid(base_url, id):
    """Iterate through all versions and get a list of failed tasks"""
    
    url = base_url + "/rest/v1/builds/" + id

    print("Grabbing failed tasks: " + url)
    json_build = json.loads(get_url(url))
    failed_tasks = []

    name = json_build['name']
        
    print ("Checking %d tasks" % (len(json_build['tasks'])))
    for task_key in json_build['tasks'].keys():
        task = json_build['tasks'][task_key]
        if task['status'] == "failed":
            failed_task = {"name": name, "task_id": task['task_id']}
            failed_tasks.append(failed_task)

    return failed_tasks


def get_failed_test_info_by_commits_sequential(base_url, commits):
    """Analyzes all failures"""
    i = 0

    builds = []
    print("Analyzing %d commits" % (len(commits)))
    for commit in commits:
        print(commit)
        builds += get_builds(base_url, commit)
        i = i + 1

    faild_tests = []
    print("Analyzing %d builds" % (len(builds)))
    for build in builds:
        print (build)
        faild_tests += get_failed_tasks_from_buildid(base_url, build)
        if len(faild_tests) > 3:
            break

    print("Analyzing %d failed tasks" % (len(faild_tests)))
    tests_to_analyze = []
    for failed2_task in faild_tests:
        print (failed2_task)
        tests_to_analyze += get_failed_tests(failed2_task)
        i = i + 1
        if i > 5:
            break

    print("Analyzing %d tests" % (len(faild_tests)))

    results = []
    for failed2_test in tests_to_analyze:
        print(" ")
        #print(failed2_task['name'], failed2_test)
        #process_log(failed_test['log_url'])
        results.append(process_log_cached(failed2_test))

    return results

def thread_map(func, items):
    # We can use a with statement to ensure threads are cleaned up promptly
    with concurrent.futures.ThreadPoolExecutor(max_workers=cpu_count() * 2) as executor:
        # Start the load operations and mark each future with its URL
        future_to_item = {executor.submit(func, item): item for item in items}
        results = []
        for future in concurrent.futures.as_completed(future_to_item):
            item = future_to_item[future]
            try:
                nf = future.result()
                if nf:
                    results += nf
            except Exception as exc:
                print('%r generated an exception: %s' % (item, exc))
    return results

def get_failed_test_info_by_commits(base_url, commits):
    """Analyzes all failures"""
    i = 0

    print("Analyzing %d commits" % (len(commits)))
    builds = thread_map( lambda item : get_builds(base_url, item), commits)

    print("Analyzing %d builds" % (len(builds)))
    faild_tests = thread_map( lambda item : get_failed_tasks_from_buildid(base_url, item), builds)

    print("Analyzing %d failed tasks" % (len(faild_tests)))
    tests_to_analyze =  thread_map( get_failed_tests, faild_tests)

    print("Analyzing %d tests" % (len(faild_tests)))

    results = []
    for failed2_test in tests_to_analyze:
        print(" ")
        #print(failed2_task['name'], failed2_test)
        #process_log(failed_test['log_url'])
        analysis = process_log_cached(failed2_test);
        if analysis:
            results.append(analysis)

    return results


# Failed_Task
# 		['name']	u'* Enterprise Amazon Linux'	unicode
#		['task_id']	u'mongodb_mongo_master_enterprise_linux_64_amazon_ami_snmp_6d87562b81fddc606d0808bf08c814735f78946d_16_06_15_14_30_38'	unicode

# Failed Test
#		['test']	u'src/mongo/db/modules/enterprise/jstests/snmp/simple_snmpwalk.js'	unicode
#		['status']	u'fail'	unicode
#		['log_url']	u'https://logkeeper.mongodb.org/build/84d7a7db760a87f8eef76d96c691804e/test/576178e4be07c46fd305b356/?raw=1'	unicode

