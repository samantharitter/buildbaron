#!/usr/bin/env python
import os
import re
import argparse
import pprint
import json

# curl -H Auth-Username:my.name -H Api-Key:21312mykey12312 https://localhost:9090/rest/v1/projects/my_private_project

# curl -H Auth-Username:JIRA_USER -H Api-Key:XXXXXXXXXXXXX https://evergreen.mongodb.com/rest/v1/projects/mongodb-mongo-master

# LogFile -> Log File Splitter -> FaultFinders -> Faultinfo
# LogFile - text stream
# LogFileSplitter - split log file into output from (test, mongod, mongos, etc) streams
# FaultFinders

# (customised per test suite)
# - Look for C++ stack trace
# - Look for JS Execption & Asserts
# - Look For FAssert and Invariants?

ROOT="Root"
MONGO_ROOT="MongoRoot"
SHELL="Shell"

RE_SERVER = re.compile('^(([cds]|sh)[0-9]{5})')
RE_SERVER_PREFIX = re.compile('^(([cds]|sh)[0-9]{5})\|')

class LineInfo:
    def __init__(self, line_number, line):
        self.line_number = line_number
        self.line = line

        self.start = 0

    def get_line(self):
        return self.line

    def get_line_number(self):
        return self.line_number

    def get_start(self):
        return self.start

    def set_start(self, val):
        self.start = val

    def __str__(self):
        return self.line

class LogFileSplitter:
    ''''Splits various streams in a log file in separate files
    '''
    def __init__(self, lstr):
        # Sinks
        # - no prefix
        # prefixed lines
        # remove dates
        # --d20010, s...., c....
        #
        re_files = re.compile('^\[.*?\] ')
        re_time = re.compile('^(-?(?:[1-9][0-9]*)?[0-9]{4})-(1[0-2]|0[1-9])-(3[01]|0[1-9]|[12][0-9])T(2[0-3]|[01][0-9]):([0-5][0-9]):([0-5][0-9])(\.[0-9]+)?(Z|[+-][0-9]{4})? ')
        re_server = re.compile('^(([cds]|sh)[0-9]{5})\|')

        lines = lstr.splitlines()
        self.splits = { ROOT : [], MONGO_ROOT : [], SHELL : [] }
        line_number = 1
        for line in lines:
            files_match = re_files.match(line)

            if files_match:

                remaining = line[files_match.end(0):]
                # print remaining
                time_match = re_time.match(remaining)
                if time_match:

                    # print remaining
                    remaining = remaining[time_match.end(0):]
                    server_match = re_server.match(remaining)
                    if server_match:
                        process_name = server_match.groups()[0]
                        if process_name not in self.splits:
                            self.splits[process_name] = []
                        self.splits[process_name].append(LineInfo(line_number, remaining))
                    else:
                        self.splits[SHELL].append(LineInfo(line_number, remaining))
                else:
                    self.splits[MONGO_ROOT].append(LineInfo(line_number, remaining))
            else:
                self.splits[ROOT].append(LineInfo(line_number, line))
            # i = i + 1
            # if i == 20:
                # return
            line_number = line_number + 1

    def dump(self):
        for key in iter(self.splits):
            print(str(key) + ":" + str(len(self.splits[key])))

    def getsplits(self):
        return self.splits

#log_file="57323e43904130088503a3f5?raw=1"

#with open(log_file, "rb") as lfh:
#    log_file_str = lfh.read()

#print "Checking Log File"
#LFS = LogFileSplitter(log_file_str)

## LFS.dump()

#s = LFS.getsplits()

# for a in [ ROOT, MONGO_ROOT, SHELL ]:
# for a in [ SHELL ]:
    # print a + ":" + str(len(s[a]))
    # print '\n'.join(s[a])

# Start categorizing
# - Is it a crash?
# - Invariant
# - FAssert
# ?????

# TODO: Add examples of logs with different faults
# FAssert ->
# MongoDB process on port 20012 exited with error code -6

# In the future, add tests cases for test result classification
#
class FaultInfo:
    def __init__(self, source, category, context, line_number):
        self.source = source
        self.category = category
        self.context = context
        self.line_number = line_number

    def __str__(self):
        return "FaultInfo -- " + self.source + " - " + self.category

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, FaultInfo):
            return {"category":obj.category, "context" :obj.context, "source":obj.source, "line_number":obj.line_number}
        
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)

class CustomDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, obj):
        if 'faults' not in obj and "contexts" not in obj:
            return obj
        
        faults = []
        for item in obj["faults"]:
            faults.append(FaultInfo(item["category"], item["context"], item["source"], item["line_number"]))

        contexts = []
        for item in obj["contexts"]:
            contexts.append(FaultInfo(item["category"], item["context"], item["source"], item["line_number"]))

        return LogFileSummary(faults, contexts)

class LogFileSummary:
    def __init__(self, faults, contexts):
        self.faults = faults
        self.contexts = contexts

    def get_faults(self):
        return self.faults

    def get_contexts(self):
        return self.contexts

class LogFileAnalyzer:
    def __init__(self, splits):
        self.splits = splits
        self.joins = {}
        self.faults = []
        self.contexts = []

        for key in self.splits:
            start = 0
            new_str = ""

            for line in self.splits[key]:
                new_str = new_str + str(line) + '\n'
                line.set_start(start)
                start = start + len(str(line)) + 1

            self.joins[key] = new_str

            # self.joins[key] = '\n'.join([a.get_line() for a in self.splits[key]])

    #TODO check all shells  - shell and sh


    def check_all(self, re_str):
        re_c = re.compile(re_str, flags=re.DOTALL)
        matches = []
        for key in iter(self.splits):
            match = re_c.search(self.joins[key])
            if match:
                matches.append({ "key" : key, "match" : match })

        return matches if len(matches) > 0 else None

    def add_fault(self, key, start, category, context):
        line_info = self.splits[key][0]
        for line in self.splits[key]:
            if start > line.get_start():
                line_info = line
            else:
                break
        # TODO: add optional # of lines of context to report

        self.faults.append(FaultInfo(key, category, context, line_info.get_line_number()))

    def add_context(self, key, start, category, context):
        line_info = self.splits[key][0]
        for line in self.splits[key]:
            if start > line.get_start():
                line_info = line
            else:
                break

        self.contexts.append(FaultInfo(key, category, context, line_info.get_line_number()))

    def analyze(self):
        # Check for SIGKILL, SIGABORT
        # StopError: MongoDB process on port 20012 exited with error code -6 :

        #if self.check_bad_exit():
            # Check for MongoDB Errors like stack traces
        #    print "Bad Exit"
            
        # Check for "StopError"
        # Test had unhappy exit
        if self.check_stoperror():
            #print "Find fatal assert"
            #TODO add more info
            self.gather_context()
            return

        # Check for leaks
        self.check_asan_leaks()

        # Check for failed tests in parallel suites
        # Check for js asserts
        if self.check_parallel_failed():
            self.gather_js_asserts()
            self.gather_context()
            return

        # Check for js asserts
        if self.check_js_asserts():
            self.gather_context()
            return

        # did the shell see:  Error: Error: error doing query

        if self.check_mongo_query_failure():
            self.gather_context()
            return

        # Check to see if a program failed to start
        if self.check_failed_start():
            self.gather_context()
            return

        # Check to see if repl wait failed
        if self.check_failed_repl_wait():
            self.gather_context()
            return

        # Check if teardown failed
        if self.check_teardown():
            self.gather_context()
            return

        # Check unit tests
        if self.check_unit_tests():
            return

        # Unit Tests if they die in the middle just have asserts
        if self.check_just_fatal_exit():
            return

        # Unit Tests if they finish with leaks
        if self.check_just_leaks():
            return

        # Check MongoDB Errors

    def gather_context(self):
        self.gather_fasserts()
        self.gather_invariants()
        self.gather_terminates()
        self.gather_go_crashes()
        
    def gather_fasserts(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        # TODO: check shell
        fasserts = self.check_all("aborting after fassert")

        if fasserts:
            for fassert in fasserts:
                log = self.joins[fassert["key"]]
                #print "fassert: " + fassert

                fatal_match = re.search("Fatal [A|a]ssertion.*aborting.*?failure", log, flags=re.DOTALL)
                if fatal_match:
                    self.add_context(fassert["key"], fatal_match.start(), "fassert", fatal_match.group(0))

                fatal_match = re.search("aborting.*?END BACKTRACE", log, flags=re.DOTALL)
                if fatal_match:
                    self.add_context(fassert["key"], fatal_match.start(), "fassert", fatal_match.group(0))

    def gather_invariants(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        fasserts = self.check_all("Invariant failure")

        if fasserts:
            for fassert in fasserts:
                log = self.joins[fassert["key"]]
                #print "fassert: " + fassert

                fatal_match = re.search("Invariant failure.*aborting.*?END BACKTRACE", log, flags=re.DOTALL)
                if fatal_match:
                    self.add_context(fassert["key"], fatal_match.start(), "invariant", fatal_match.group(0))

                fatal_match = re.search("Invariant failure.*aborting.*?writing minidump", log, flags=re.DOTALL)
                if fatal_match:
                    self.add_context(fassert["key"], fatal_match.start(), "invariant", fatal_match.group(0))


    def gather_terminates(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        fasserts = self.check_all("terminate\(\) called")

        if fasserts:
            for fassert in fasserts:
                log = self.joins[fassert["key"]]
                #print "fassert: " + fassert

                fatal_match = re.search("terminate\(\) called.*?END BACKTRACE", log, flags=re.DOTALL)
                if fatal_match:
                    self.add_context(fassert["key"], fatal_match.start(), "terminate", fatal_match.group(0))

                fatal_match = re.search("terminate\(\) called.*?writing minidump", log, flags=re.DOTALL)
                if fatal_match:
                    self.add_context(fassert["key"], fatal_match.start(), "terminate", fatal_match.group(0))

    def gather_go_crashes(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        # TODO: check shell
        go_crashes = self.check_all("unexpected fault address")

        if go_crashes:
            for go_crash in go_crashes:
                log = self.joins[go_crash["key"]]
                #print "fassert: " + fassert

                fatal_match = re.search("unexpected fault address.*goroutine", log, flags=re.DOTALL)
                if fatal_match:
                    self.add_context(go_crash["key"], fatal_match.start(), "go binary crash", fatal_match.group(0))
                # TODO - log analysis failure

    
    def gather_js_asserts(self):
        jsasserts = self.check_all("assert(:|\.soon).*?failed.*?js")

        if jsasserts:
            for jsassert in jsasserts:
                log = self.joins[jsassert["key"]]
                assert_match = re.search("assert(:|\.soon).*?failed.*?js", log, flags=re.DOTALL)
                if assert_match:
                    self.add_context(jsassert["key"], assert_match.start(), "js assert", assert_match.group(0))
                    return True

        return False


    def base_joins(self):
        """ Loop through all the streams for reasons why tests fail"""
        for stream in [ROOT, MONGO_ROOT, SHELL]:
            yield self.joins[stream]

    def check_just_fatal_exit(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        for shell in self.base_joins():
            #*** C runtime error: C:\Program Files (x86)\Microsoft Visual Studio 14.0\VC\INCLUDE\xtree(326) : Assertion failed: map/set iterators incompatible, terminating
            c_runtime_error_match = re.search("\*\*\* C runtime error.*", shell)
            if c_runtime_error_match:
                self.add_fault(SHELL, c_runtime_error_match.start(), "c_runtime_error", c_runtime_error_match.group(0))
                return True

            fassert_match = re.search("aborting after fassert", shell)

            if fassert_match:
                self.add_fault(SHELL, fassert_match.start(), "fassert", fassert_match.group(0))
                return True

        return False

    def check_mongo_query_failure(self):
        for shell in self.base_joins():
            assert_match = re.search("Error: (explain|error doing query|map reduce failed|error:).*failed.*?js", shell, flags=re.DOTALL)
            if assert_match:
                self.add_fault(SHELL, assert_match.start(), "mongo query failure", assert_match.group(0))
                return True

        return False

    def check_failed_start(self):
        for shell in self.base_joins():
            assert_match = re.search("Error: Failed to start mongos.*failed.*?js", shell, flags=re.DOTALL)
            if assert_match:
                self.add_fault(SHELL, assert_match.start(), "failed to start mongos", assert_match.group(0))
                return True

        return False

    def check_failed_repl_wait(self):
        for shell in self.base_joins():
            assert_match = re.search("Error: waiting for replication timed out.*failed.*?js", shell, flags=re.DOTALL)
            if assert_match:
                self.add_fault(SHELL, assert_match.start(), "failed to wait for replication", assert_match.group(0))
                return True

        return False

    def check_parallel_failed(self):
        for shell in self.base_joins():
            assert_match = re.search("Parallel Test FAILED: .*", shell)
            if assert_match:
                self.add_fault(SHELL, assert_match.start(), "parallel test failed", assert_match.group(0))
                return True

        return False

    def check_js_asserts(self):
        for shell in self.base_joins():

            assert_match = re.search("assert(:|\.soon).*?failed.*?js", shell, flags=re.DOTALL)
            if assert_match:
                self.add_fault(SHELL, assert_match.start(), "js assert", assert_match.group(0))
                return True

        return False

    def check_teardown(self):
        for shell in self.base_joins():

            # [ReplicaSetFixture:job12:initsync] mongod on port 23002 was expected to be running in teardown(), but wasn't.
            assert_match = re.search("mongo.*?teardown.*?wasn't.", shell)
            if assert_match:
                self.add_fault(SHELL, assert_match.start(), "teardown failed", assert_match.group(0))
                return True

        return False

    def check_asan_leaks(self):
        # Check for leaks
        leaks = self.check_all("LeakSanitizer: detected memory leaks")

        # TODO capture logs here

    def check_just_leaks(self):
        for shell in self.base_joins():

            assert_match = re.search("LeakSanitizer: detected memory leaks.*?SUMMARY.*?\.", shell, flags=re.DOTALL)
            if assert_match:
                self.add_fault(SHELL, assert_match.start(), "memory leaks", assert_match.group(0))
                return True

        return False
    
    def check_unit_tests(self):
        shell = self.joins[SHELL]

        assert_match = re.search("DONE running tests.*?FAILURE.*?failed", shell, flags=re.DOTALL)
        if assert_match:
            self.add_fault(SHELL, assert_match.start(), "C++ Unit Test Failure", assert_match.group(0))
            return True
        return False

    def check_stoperror(self):
        for shell in self.base_joins():
            assert_match = re.search("StopError:.*failed.*?js", shell, flags=re.DOTALL)
            if assert_match:
                text = assert_match.group(0);

                if "error code -1073741819" in text:
                    self.add_fault(SHELL, assert_match.start(), "Windows_Access_Violation", text)
                elif "error code -6" in text:
                    self.add_fault(SHELL, assert_match.start(), "Process_Abort", text)
                else:
                    self.add_fault(SHELL, assert_match.start(), "StopError", text)
                return True
        return False


    def check_bad_exit(self):
        # Check Shell Errors
        for shell in self.base_joins():

            # print shell
            re_bad_exit = re.compile("exited with error code -(\d+)")

            bad_exit_match = re_bad_exit.search(shell)
            if bad_exit_match:
                # self.add_fault(
                # print "MATCH"
                # self.faults.append(FaultInfo("shell", "bad exit code", bad_exit_match.groups()[0]))
                self.add_fault(SHELL, bad_exit_match.start(), "bad exit code", bad_exit_match.groups()[0])

                return True
        return False

    def get_faults(self):
        return self.faults

    def get_contexts(self):
        return self.contexts

    def to_json(self):
        d1 = { "faults" : self.faults,
              "contexts" : self.contexts }
        return json.dumps(d1, cls=CustomEncoder)

def main():
    parser = argparse.ArgumentParser(description='Process log file.')

    parser.add_argument("files", type=str, nargs='+', help="the file to read" )
    args = parser.parse_args()

    for file in args.files:
        
        with open(file, "rb") as lfh:
            log_file_str = lfh.read().decode('utf-8')

        LFS = LogFileSplitter(log_file_str)

        s = LFS.getsplits()
    
        analyzer = LogFileAnalyzer(s)

        analyzer.analyze()

        faults = analyzer.get_faults()

        if len(faults) == 0:
            print("===========================")
            print("Analysis failed for test: " + file)
            print("===========================")
            return

        for f in analyzer.get_faults():
            print(f)

        print(analyzer.to_json())

        f = json.loads(analyzer.to_json(), cls=CustomDecoder)
        #print (f);

if __name__ == '__main__':
    main()