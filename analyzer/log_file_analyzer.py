#!/usr/bin/env3 python
"""
A JS Test/Unit test log file analyzer
"""
import os
import re
import argparse
import pprint
import json
import sys
import io

if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.abspath(os.path.realpath(__file__))))
    print (sys.path)
    import faultinfo
else:
    from . import faultinfo

# LogFile -> Log File Splitter -> FaultFinders -> Faultinfo
# LogFile - text stream
# LogFileSplitter - split log file into output from (test, mongod, mongos, etc) streams

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
    """Splits various streams in a log file in separate files
    """
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
            line_number += 1

    def dump(self):
        for key in iter(self.splits):
            print(str(key) + ":" + str(len(self.splits[key])))

    def getsplits(self):
        return self.splits

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
                line.set_start(start)
                start = start + len(str(line)) + 1
            
            self.joins[key] = '\n'.join([str(a) for a in self.splits[key]])

    def check_all(self, re_str):
        """Check all streams"""
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

        self.faults.append(faultinfo.FaultInfo(key, category, context, line_info.get_line_number()))

    def add_context(self, key, start, category, context):
        line_info = self.splits[key][0]
        for line in self.splits[key]:
            if start > line.get_start():
                line_info = line
            else:
                break

        self.contexts.append(faultinfo.FaultInfo(key, category, context, line_info.get_line_number()))

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
            
        # Check for memory corruption
        if self.check_tcmalloc_corruption():
            return

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
            self.gather_context()
            return

        # Unit Tests if they die in the middle just have asserts
        if self.check_just_fatal_exit():
            self.gather_context()
            return

        # Unit Tests if they finish with leaks
        if self.check_just_leaks():
            self.gather_context()
            return

        # If we cannot figure out why it stoppped, maybe it didn't
        # but report on interesting information.
        self.gather_context()

    def gather_context(self):
        self.gather_fasserts()
        self.gather_invariants()
        self.gather_terminates()
        self.gather_go_crashes()
        self.gather_leaks()
        self.gather_crashes()
        self.gather_tcmalloc_corruption()

    def gather_context_re(self, quick_check, detail_checks):
        """Iterate through each slice of the log, see if it contains a particular message, and if so, use a regex to get more information"""
        matches = self.check_all(quick_check)

        if matches:
            for match in matches:
                log_str = self.joins[match["key"]]

                for check in detail_checks:
                    check_match = re.search(check[1], log_str, flags=re.DOTALL)
                    if check_match:
                        self.add_context(match["key"], check_match.start(), check[0], check_match.group(0))

        
    def gather_fasserts(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        # TODO: check shell
        self.gather_context_re("aborting after fassert",
                               [["fassert", "Fatal [A|a]ssertion.*aborting.*?failure"],
                                ["fassert", "aborting.*?END BACKTRACE"]])

    def gather_invariants(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        self.gather_context_re("Invariant failure",
                               [["invariant", "Invariant failure.*aborting.*?END BACKTRACE"],
                                ["invariant", "Invariant failure.*aborting.*?writing minidump"]])

    def gather_terminates(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        self.gather_context_re("terminate\(\) called",
                               [["terminate", "terminate\(\) called.*?END BACKTRACE"],
                                ["terminate", "terminate\(\) called.*?writing minidump"]])

    def gather_go_crashes(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        self.gather_context_re("unexpected fault address",
                               [["go binary crash", "unexpected fault address.*goroutine"]])

    def gather_js_asserts(self):
        self.gather_context_re("assert(:|\.soon).*?failed.*?js",
                               [["js assert", "assert(:|\.soon).*?failed.*?js"]])

    def gather_leaks(self):
        # JS tests do not directly fail due to the leak sanitizier
        self.gather_context_re("LeakSanitizer",
                               [["memory leaks", "LeakSanitizer: detected memory leaks.*?SUMMARY.*?\."]])

    def gather_crashes(self):
        self.gather_context_re("Segmentation Fault",
                               [["segmentation fault", "Segmentation Fault.*?END BACKTRACE"]])

    def gather_tcmalloc_corruption(self):
        self.gather_context_re("Found a corrupted memory buffer",
                               [["tcmalloc memory corruption", "Found a corrupted memory buffer in MallocBlock.*?END BACKTRACE"]])

    def base_joins(self):
        """ Loop through all the streams for reasons why tests fail"""
        for stream in [ROOT, MONGO_ROOT, SHELL]:
            yield stream, self.joins[stream]

    def check_fault_re(self, checks):
        for stream_name, stream in self.base_joins():
            for check in checks:
                check_match = re.search(check[1], stream)
                if check_match:
                    self.add_fault(stream_name, check_match.start(), check[0], check_match.group(0))
                    return True
    
        return False

    def check_just_fatal_exit(self):
        # Tests can fail for reasons other then fasserts
        # like access violation
        #*** C runtime error: C:\Program Files (x86)\Microsoft Visual Studio 14.0\VC\INCLUDE\xtree(326) : Assertion failed: map/set iterators incompatible, terminating

        return self.check_fault_re([["c_runtime_error", "\*\*\* C runtime error.*"],
                                    ["fassert", "aborting after fassert"]])

    def check_mongo_query_failure(self):
        return self.check_fault_re([["mongo query failure", "Error: (explain|error doing query|map reduce failed|error:).*failed.*?js"]])

    def check_failed_start(self):
        return self.check_fault_re([["failed to start mongos", "Error: Failed to start mongos.*failed.*?js"]])

    def check_failed_repl_wait(self):
        return self.check_fault_re([["failed to wait for replication", "Error: waiting for replication timed out.*failed.*?js"]])

    def check_parallel_failed(self):
        return self.check_fault_re([["parallel test failed", "Parallel Test FAILED: .*"]])

    def check_js_asserts(self):
        return self.check_fault_re([["js assert", "assert(:|\.soon).*?failed.*?js"]])

    def check_teardown(self):
        for stream_name, stream in self.base_joins():

            # [ReplicaSetFixture:job12:initsync] mongod on port 23002 was expected to be running in teardown(), but wasn't.
            # Match line by line
            assert_match = re.search("mongo.*?teardown.*?wasn't.", stream)
            if assert_match:
                self.add_fault(stream_name, assert_match.start(), "teardown failed", assert_match.group(0))
                return True

        return False

    def check_just_leaks(self):
        # Unit tests directly fail due to the leak sanitizier
        return self.check_fault_re([["memory leaks", "LeakSanitizer: detected memory leaks.*?SUMMARY.*?\."]])

    def check_tcmalloc_corruption(self):
        return self.check_fault_re([["tcmalloc memory corruption", "Found a corrupted memory buffer in MallocBlock.*?END BACKTRACE"]])
    
    def check_unit_tests(self):
        shell = self.joins[SHELL]

        assert_match = re.search("DONE running tests.*?FAILURE.*?failed", shell, flags=re.DOTALL)
        if assert_match:
            self.add_fault(SHELL, assert_match.start(), "C++ Unit Test Failure", assert_match.group(0))
            return True
        return False

    def check_stoperror(self):
        for stream_name, stream in self.base_joins():
            assert_match = re.search("StopError:.*failed.*?js", stream, flags=re.DOTALL)
            if assert_match:
                text = assert_match.group(0);

                if "error code -1073741819" in text:
                    self.add_fault(stream_name, assert_match.start(), "Windows_Access_Violation", text)
                elif "error code -6" in text:
                    self.add_fault(stream_name, assert_match.start(), "Process_Abort", text)
                else:
                    self.add_fault(stream_name, assert_match.start(), "StopError", text)
                return True
        return False

    def check_bad_exit(self):
        # Check Shell Errors
        return self.check_fault_re([["bad exit code", "exited with error code -(\d+)"]])

    def get_faults(self):
        return self.faults

    def get_contexts(self):
        return self.contexts

    def to_json(self):
        d1 = { "faults" : self.faults,
              "contexts" : self.contexts }
        return json.dumps(d1, cls=faultinfo.CustomEncoder)

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

        f = json.loads(analyzer.to_json(), cls=faultinfo.CustomDecoder)

if __name__ == '__main__':
    main()