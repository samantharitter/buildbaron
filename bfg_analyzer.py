#!/usr/bin/env python3
"""
Script to analyze the Jira Build Baron Queue
"""
import binascii
import os
import hashlib
import re
import argparse
import pprint
import json
import getpass
import string
import urllib
import stat
import sys
import requests

try:
  import keyring
except ImportError:
  keyring = None

# Global override
UPDATE_JIRA=False

if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__)))))
    print (sys.path)

import buildbaron.analyzer.log_file_analyzer
import buildbaron.analyzer.evg_log_file_analyzer
import buildbaron.analyzer.evergreen
import buildbaron.analyzer.logkeeper
import buildbaron.analyzer.timeout_file_analyzer
import buildbaron.analyzer.analyzer_config
import buildbaron.analyzer.jira_client

# URL of the default Jira server.
# If you use .com, it breaks horribly
def ParseJiraTicket(issue, summary, description):
    # Parse summary
    if "System Failure:" in summary:
        type = "system_failure"
    elif "Timed Out:" in summary:
        type = "timed_out"
    elif "Failures" in summary:
        type = "test_failure"
    elif "Failure" in summary:
        type = "test_failure"
    elif "Failed" in summary:
        type = "task_failure"
    else:
        raise ValueError("Unknown summary " + str(summary))

    suite = "unknown"
    build_variant = "unknown"
    summary_match = re.match(".*?: (.*) on (.*) \(", summary)
    if summary_match:
        suite = summary_match.group(1)
        build_variant = summary_match.group(2)

    # Parse Body of description
    lines = description.split("\n")
    tests = []
    for line in lines:
        if line.startswith('h2.'):
            url_match = re.search("\|(.*)\]", line)
            task_url = url_match.group(1)
        elif line.startswith('Project'):
            p_match = re.search("\[(.*)\|", line)
            project = p_match.group(1)
        elif "[Logs|" in line:
            log_line_match = re.match("\*(.*)\* - \[Logs\|(.*?)\]", line)
            test_name = log_line_match.group(1)
            log_file = log_line_match.group(2 )
            tests.append({ 'name' : test_name, 'log_file' : log_file })
        else:
            pass

    return bfg_fault_description(issue, summary, type, project, task_url, suite, build_variant, tests)

class bfg_fault_description:
    """Parse a fault description into type"""

    def __init__(self,  issue, summary, type, project, task_url, suite, build_variant, tests):
        self.issue = issue
        self.summary = summary
        self.type = type
        self.project = project
        self.task_url = task_url
        self.suite = suite
        self.build_variant = build_variant
        self.tests = tests


    def to_json(self):
        return json.dumps(self, cls=BFGCustomEncoder)

class BFGCustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bfg_fault_description):
            return { "issue":obj.issue, "summary":obj.summary, "type":obj.type, "task_url" :obj.task_url, "project":obj.project,
                    "suite":obj.suite, "build_variant":obj.build_variant,
                    "tests":obj.tests}
        
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)

class BFGCustomDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, obj):
        if 'task_url' not in obj and "project" not in obj:
            return obj

        return bfg_fault_description(obj['issue'], obj['summary'], obj['type'], obj['project'], obj['task_url'], obj['suite'], obj['build_variant'], obj['tests'])

class bfg_analyzer(object):
    """description of class"""
    def __init__(self, jira_client):
        self.jira_client = jira_client
        self.evg_client = buildbaron.analyzer.evergreen.client()
        self.pp = pprint.PrettyPrinter()

    def query(self):
        #results = self.jira_client.search_issues("project = bfg AND resolution is EMPTY AND created > 2017-01-25 AND created <= 2017-02-01 and summary ~ Timed ORDER BY created DESC", maxResults=25)
        results = self.jira_client.search_issues("project = bfg AND resolution is EMPTY AND created > 2017-01-25 AND created <= 2017-02-01 and summary !~ FooTimed ORDER BY created DESC", maxResults=100)

        #results = self.jira_client.search_issues("project = bfg AND resolution is EMPTY AND created > 2017-01-25 AND created <= 2017-02-01 AND summary ~ Failure and summary ~ ubsan ORDER BY created DESC")

        print(len(results))
        
        bfs = []

        for result in results:
            bfs.append(ParseJiraTicket(result.key, result.fields.summary, result.fields.description))

        with open("bfs.json", "wb") as sjh:
            sjh.write(json.dumps(bfs, cls=BFGCustomEncoder, indent="\t").encode())

    def check_logs(self):
        bfs = []
        with open("bfs.json", "rb") as sjh:
            s1 = sjh.read().decode()
            bfs = json.loads(s1)

        results = []

        for bf in bfs:
            self.process_bf(bf, results)

        return results;
    
    def create_bf_cache(self, bf):
        """Create a directory to cache the log file in"""
        if not os.path.exists("cache"):
            os.mkdir("cache");
        if not os.path.exists(os.path.join("cache", "bf")):
            os.mkdir(os.path.join("cache", "bf"));

        m = hashlib.sha1()
        m.update(bf["task_url"].encode())
        digest = m.digest()
        digest64 = binascii.b2a_hex(digest).decode()
        bf["hash"] = digest64
        path = os.path.join("cache", "bf", digest64)
        bf["bf_cache"] = path

        if not os.path.exists(path):
            os.mkdir(path)

    def create_test_cache(self, bf, test):
        """Create a directory to cache the log file in"""

        m = hashlib.sha1()
        m.update(test["name"].encode())
        digest = m.digest()
        digest64 = binascii.b2a_hex(digest).decode()
        test["hash"] = digest64
        path = os.path.join(bf['bf_cache'], digest64)
        test["cache"] = path

        if not os.path.exists(path):
            os.mkdir(path)
   
    def process_bf(self, bf, results):
        """Process a log through the log file analyzer

        Saves test information in cache\XXX\test.json
        Saves analysis information in cache\XXX\summary.json
        """
        pp = pprint.PrettyPrinter()
        
        self.create_bf_cache(bf)
        
        bf_name = bf['summary']
        print("BF: " + str(bf))

        # Handle normal test failures
        if bf['type'] == 'test_failure':
            # Go through each test
            for test in bf['tests']:
                self.process_test(bf, test, results)
        elif bf['type'] == 'system_failure':
            self.process_system_failure(bf, results)
        elif bf['type'] == 'task_failure':
            self.process_task_failure(bf, results)
        elif bf['type'] == 'timed_out':
            self.process_time_out(bf, results)

        print("")

        #with open(test_json, "wb") as tjh:
        #    json.dump(failed_test, tjh);

        #return { "test" : failed_test, "summary" : summary_obj }
    def process_system_failure(self, bf, results):
        cache_dir = bf["bf_cache"]
        log_file = os.path.join(cache_dir, "test.log")
        summary_json = os.path.join(cache_dir, "summary.json")

        log_file_url = buildbaron.analyzer.evergreen.task_get_task_raw_log(bf["task_url"]);
        system_log_url = buildbaron.analyzer.evergreen.task_get_system_raw_log(bf['task_url']);

        bf['system_log_url'] = system_log_url
        bf['log_file_url'] = log_file_url
        bf['name'] = 'task'
        bf['cache'] = bf['bf_cache']

        if os.path.exists(summary_json) and not UPDATE_JIRA:
            with open(summary_json, "rb") as sjh:
                contents = sjh.read().decode('utf-8')
                summary_str = json.loads(contents)

            results.append({ "test" : bf, "summary" : summary_str  })
            return

        if not os.path.exists(log_file):
            self.evg_client.retrieve_file(log_file_url, log_file)

        with open(log_file, "rb") as lfh:
            log_file_str = lfh.read().decode('utf-8')
    
        analyzer = buildbaron.analyzer.evg_log_file_analyzer.EvgLogFileAnalyzer(log_file_str)

        analyzer.analyze()

        faults = analyzer.get_faults()
        
        if len(faults) == 0:
            print("===========================")
            print("Analysis failed for test: " + self.pp.pformat(bf))
            print("To Debug: python analyzer\\log_file_analyzer.py %s " % (log_file))
            print("===========================")
        else:
            self.add_system_failure_comment(bf, log_file_url, faults)

        for f in analyzer.get_faults():
            print(f)

        summary_str = analyzer.to_json()
        summary_obj = json.loads(summary_str)

        with open(summary_json, "wb") as sjh:
            sjh.write(summary_str.encode())

        results.append({ "test" :bf, "summary" : summary_obj  })

    def process_task_failure(self, bf, results):
        cache_dir = bf["bf_cache"]
        log_file = os.path.join(cache_dir, "test.log")
        summary_json = os.path.join(cache_dir, "summary.json")

        log_file_url = buildbaron.analyzer.evergreen.task_get_task_raw_log(bf["task_url"]);
        system_log_url = buildbaron.analyzer.evergreen.task_get_system_raw_log(bf['task_url']);

        bf['system_log_url'] = system_log_url
        bf['log_file_url'] = log_file_url
        bf['name'] = 'task'
        bf['cache'] = bf['bf_cache']
            
        if os.path.exists(summary_json):
            with open(summary_json, "rb") as sjh:
                contents = sjh.read().decode('utf-8')
                summary_str = json.loads(contents)

            results.append({ "test" : bf, "summary" : summary_str  })
            return

        if not os.path.exists(log_file):
            self.evg_client.retrieve_file(log_file_url, log_file)

        with open(log_file, "rb") as lfh:
            log_file_str = lfh.read().decode('utf-8')
    
        analyzer = buildbaron.analyzer.evg_log_file_analyzer.EvgLogFileAnalyzer(log_file_str)

        analyzer.analyze()

        faults = analyzer.get_faults()
        
        if len(faults) == 0:
            oom_analyzer = self.check_for_oom_killer(bf)
            if oom_analyzer is None:
                print("===========================")
                print("Analysis failed for test: " + self.pp.pformat(bf))
                print("To Debug: python analyzer\\log_file_analyzer.py %s " % (log_file))
                print("===========================")
            else:
                analyzer = oom_analyzer
        else:
            pass
            #  self.add_system_failure_comment(bf, log_file_url, faults)

        for f in analyzer.get_faults():
            print(f)

        summary_str = analyzer.to_json()
        summary_obj = json.loads(summary_str)

        with open(summary_json, "wb") as sjh:
            sjh.write(summary_str.encode())

        results.append({ "test" :bf, "summary" : summary_obj  })

    def process_time_out(self, bf, results):
        cache_dir = bf["bf_cache"]
        log_file = os.path.join(cache_dir, "test.log")
        summary_json = os.path.join(cache_dir, "summary.json")

        log_file_url = buildbaron.analyzer.evergreen.task_get_task_raw_log(bf["task_url"]);
        system_log_url = buildbaron.analyzer.evergreen.task_get_system_raw_log(bf['task_url']);

        bf['system_log_url'] = system_log_url
        bf['log_file_url'] = log_file_url
        bf['name'] = 'task'
        bf['cache'] = bf['bf_cache']

        if os.path.exists(summary_json):
            with open(summary_json, "rb") as sjh:
                contents = sjh.read().decode('utf-8')
                summary_str = json.loads(contents)

            results.append({ "test" : bf, "summary" : summary_str  })
            return

        if not os.path.exists(log_file):
            self.evg_client.retrieve_file(log_file_url, log_file)

        with open(log_file, "rb") as lfh:
            log_file_str = lfh.read().decode('utf-8')
    
        print("Checking " + log_file)
        analyzer = buildbaron.analyzer.timeout_file_analyzer.TimeOutAnalyzer(log_file_str)

        analyzer.analyze()

        incomplete_tests = analyzer.get_incomplete_tests()
        
        if len(incomplete_tests) == 0:
            faults = analyzer.get_faults()
        
            if len(faults) == 0:
                print("===========================")
                print("Analysis failed for test: " + self.pp.pformat(bf))
                print("To Debug: python analyzer\\timeout_file_analyzer.py %s " % (log_file))
                print("===========================")

            summary_str = analyzer.to_json()
            summary_obj = json.loads(summary_str)

            with open(summary_json, "wb") as sjh:
                sjh.write(summary_str.encode())

            results.append({ "test" :bf, "summary" : summary_obj  })

        else:
            for incomplete in incomplete_tests:
                print("PROCSSSING --------------------------------------- %s" % incomplete)
                self.process_test(bf, incomplete, results)
            bf['tests'] = incomplete_tests

    def process_test(self, bf, test, results):
        bf_name = bf['summary']
        self.create_test_cache(bf, test)
        test_name = bf_name + " " + test['name']

        cache_dir = test["cache"]
        log_file = os.path.join(cache_dir, "test.log")
        summary_json = os.path.join(cache_dir, "summary.json")

        nested_test = test
        for key in bf.keys():
            if key != 'tests' and key != 'name':
                nested_test[key] = bf[key]

        oom_analyzer = self.check_for_oom_killer(bf)
        if oom_analyzer is None:
            # If logkeeper is down, we will not have a log file :-(
            if test["log_file"] is not None and test["log_file"] != "" and "test/None" not in test['log_file']:

                if not os.path.exists(log_file):
                    buildbaron.analyzer.logkeeper.retieve_raw_log(test["log_file"], log_file)

                test['log_file_url'] = buildbaron.analyzer.logkeeper.get_raw_log_url(test["log_file"])
    
                log_file_stat = os.stat(log_file)
                            
                if log_file_stat[stat.ST_SIZE] > 50 * 1024 * 1024:
                    summary_str = "Skipping Large File : " + str(log_file_stat[stat.ST_SIZE] )
                    results.append({ "test" :nested_test, "summary" : summary_str  })
                    return
            else:
                test['log_file_url'] = "none"
                with open(log_file, "wb") as lfh:
                    lfh.write("Logkeeper was down\n".encode())

                log_file_stat = os.stat(log_file)

            if os.path.exists(summary_json):
                with open(summary_json, "rb") as sjh:
                    contents = sjh.read().decode('utf-8')
                    summary_str = json.loads(contents)

                results.append({ "test" : nested_test, "summary" : summary_str  })
                return

            if log_file_stat[stat.ST_SIZE] > 50 * 1024 * 1024:
                print("Skipping Large File : " + str(log_file_stat[stat.ST_SIZE]) + " at " + str(log_file))
                print(summary_str)
                summary_obj = summary_str
            else:
                with open(log_file, "rb") as lfh:
                    log_file_str = lfh.read().decode('utf-8')
    
                print("Checking Log File")
                LFS = buildbaron.analyzer.log_file_analyzer.LogFileSplitter(log_file_str)

                s = LFS.getsplits()
    
                analyzer = buildbaron.analyzer.log_file_analyzer.LogFileAnalyzer(s)

                analyzer.analyze()

                faults = analyzer.get_faults()

                if len(faults) == 0:
                    print("===========================")
                    print("Analysis failed for test: " + self.pp.pformat(bf))
                    print("To Debug: python analyzer\\log_file_analyzer.py %s " % (log_file))
                    print("===========================")
        else:
            # Well, we hit an oom, ignore the test
            test['log_file_url'] = "none"
            analyzer = oom_analyzer

        for f in analyzer.get_faults():
            print(f)
                
        summary_str = analyzer.to_json()
        summary_obj = json.loads(summary_str)

        with open(summary_json, "wb") as sjh:
            sjh.write(summary_str.encode())

        results.append({ "test" :nested_test, "summary" : summary_obj  })

    def check_for_oom_killer(self, bf):
        cache_dir = bf["bf_cache"]
        log_file = os.path.join(cache_dir, "system.log")
        system_log_url =  buildbaron.analyzer.evergreen.task_get_system_raw_log(bf['task_url']);

        if not os.path.exists(log_file):
            self.evg_client.retrieve_file(system_log_url, log_file)

        with open(log_file, "rb") as lfh:
            log_file_str = lfh.read().decode('utf-8')
    
        analyzer = buildbaron.analyzer.evg_log_file_analyzer.EvgLogFileAnalyzer(log_file_str)

        analyzer.analyze_oom()

        if len(analyzer.get_faults()) > 0:
            return analyzer

        return None

    def add_system_failure_comment(self, bf, log_file_url, faults):
        if UPDATE_JIRA == True:
            issue = self.jira_client.issue(bf['issue'])
            comments = issue.fields.comment.comments
        else:
            comments = []
        print("Comment count:" + str(len(comments)))

        if len(comments) == 0:
            # Add a comment with what we learned
            print("Reporting BF summary to Jira: %s - %s" % (str(bf), log_file_url))
            self.pp.pformat(faults)

            fault = faults[0]

            # TODO: move this to evergreen module
            log_file_url_line = log_file_url.replace("&text=true", "#L" + str(fault.line_number))
            message = """[Raw Log File|%s]
[Fault Details|%s]:
{noformat}
%s
{noformat}
""" % (log_file_url, log_file_url_line, fault.context)
            print(message)

            if UPDATE_JIRA == True:
                print("Updating Jira issue '%s'" %  issue.key)
                self.jira_client.add_comment(issue.key, message)

def tests1():
    a1 = ParseJiraTicket(1, "Timed Out: sharding_csrs_upgrade_WT on Enterprise Windows [MongoDB (3.2) @ 190538da]",
"""
h2. [sharding_csrs_upgrade_WT failed on Enterprise Windows|https://evergreen.mongodb.com/task/mongodb_mongo_v3.2_enterprise_windows_64_sharding_csrs_upgrade_WT_190538da7580eee02ab36993c426bf9b94005247_17_01_25_15_41_26]
Host: [ec2-54-161-188-84.compute-1.amazonaws.com|https://evergreen.mongodb.com/host/sir-rhmr5irg]
Project: [MongoDB (3.2)|https://evergreen.mongodb.com/waterfall/mongodb-mongo-v3.2]
""")

    a2 = ParseJiraTicket(2, "System Failure: push on SSL SUSE 12 [MongoDB (master) @ ae048229]",
"""
h2. [push failed on SSL SUSE 12|https://evergreen.mongodb.com/task/mongodb_mongo_master_suse12_push_ae04822985f2478c7da1e6821f5fc91b484b9555_17_01_23_18_03_09]
Host: [ec2-54-92-136-107.compute-1.amazonaws.com|https://evergreen.mongodb.com/host/sir-yfvg7m3h]
Project: [MongoDB (master)|https://evergreen.mongodb.com/waterfall/mongodb-mongo-master]
""")
 
    a3 = ParseJiraTicket(3, "Failures: aggregation_read_concern_majority_passthrough_WT on ~ Enterprise RHEL 6.2 DEBUG Code Coverage (error.js, error:CheckReplOplogs) [MongoDB (3.4) @ c91a4d4e]",
"""
h2. [aggregation_read_concern_majority_passthrough_WT failed on ~ Enterprise RHEL 6.2 DEBUG Code Coverage|https://evergreen.mongodb.com/task/mongodb_mongo_v3.4_enterprise_rhel_62_64_bit_coverage_aggregation_read_concern_majority_passthrough_WT_c91a4d4eda70f11ecd4ce21d57fd9a57e889df70_17_01_25_15_37_12]
Host: [ec2-107-22-100-90.compute-1.amazonaws.com|https://evergreen.mongodb.com/host/sir-aqfi5mij]
Project: [MongoDB (3.4)|https://evergreen.mongodb.com/waterfall/mongodb-mongo-v3.4]
*error.js* - [Logs|https://logkeeper.mongodb.org/build/93669f7c42bf42420db8f8f8fbf95910/test/5888ebdfc2ab683cbd04be4c/] | [History|https://evergreen.mongodb.com/task_history/mongodb-mongo-v3.4/aggregation_read_concern_majority_passthrough_WT#error.js=fail]
*error:CheckReplOplogs* - [Logs|https://logkeeper.mongodb.org/build/93669f7c42bf42420db8f8f8fbf95910/test/5888ef97c2ab683cbd05404b/] | [History|https://evergreen.mongodb.com/task_history/mongodb-mongo-v3.4/aggregation_read_concern_majority_passthrough_WT#error:CheckReplOplogs=fail]
""")

    #print(str(a3.tests));

    #print(a1.to_json())
    #print(a2.to_json())
    #print(a3.to_json())

    a4 = json.loads(a3.to_json(), cls=BFGCustomDecoder)

def main():
    parser = argparse.ArgumentParser(description='Analyze test failure in jira.')
        
    group = parser.add_argument_group("Jira options")
    group.add_argument('--jira_server', type=str, help="Jira Server to query",
                       default=buildbaron.analyzer.analyzer_config.jira_server())
    group.add_argument('--jira_user', type=str, help="Jira user name", default=buildbaron.analyzer.analyzer_config.jira_user())

    #parser.add_argument("terms", type=str, nargs='+', help="the file to read" )

    tests1()

    args = parser.parse_args()

    try:
        jira_client = buildbaron.analyzer.jira_client.jira_client(args.jira_server, args.jira_user)

        bfa = bfg_analyzer(jira_client)

        bfa.query()

        failed_bfs = bfa.check_logs()

        print("Total BFs to investigate %d\n" % len(failed_bfs))
        
        with open("failed_bfs.json", "w", encoding="utf8") as sjh:
            json.dump(failed_bfs, sjh, indent="\t")

    except Exception  as e:
        print("Exception:" + str(e))
                

if __name__ == '__main__':
    main()




