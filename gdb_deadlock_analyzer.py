#!/usr/bin/env python
import os
import re
import argparse
import pprint
import json
import string

def parse_log(file):
    re_files = re.compile('^\[.*?\] ')
    re_offset = re.compile("\+0x[0-9a-fA-F]+")

    file = open(file, "rb")

    in_dbg = 0
    stacks = []
    cur_stack = []
    stack_num = 0
    in_stacks = 0
    print "Staring Analysis"

    while True:
        curLine = file.readline()
        if(curLine == ""):
            break
        curLine = curLine.rstrip().lstrip()

        if not in_dbg:
            if "GNU gdb" not in curLine:
                continue

        # Found start of debuggers
        in_dbg = 1

        
        if "Done analyzing process" in curLine:
            # Done With Debuggers
            in_dbg = 0

        # Strip Date Prefix
        curLine = re_files.sub("", curLine)
        
        if(curLine.startswith("***")):
            continue
        elif curLine.startswith("Thread "):
            # Stacks start
            in_stacks = 1
        elif curLine.startswith("INFO: Done"):
            # Stacks end
            in_stacks = 0

            # Summarize
            stacks_set = set(stacks)

            print "**************************************"
            print "**************************************"
            print "Unique stacks: " + str(len(stacks_set)) + " of " + str(len(stacks))
            print "**************************************"

            for stack in stacks_set:
                print "--------------"
                print "\n".join(string.split(stack, ";"))

            stacks = []

        if in_stacks:
            if curLine.startswith("Thread "):
                #New Stack
                # cur_stack.reverse()
                #print "stck"
                stack_str = string.join(cur_stack, ";") 
                stacks.append(stack_str)
        
                cur_stack = []
                continue
            # Ignore blank lines, they separate allocations from stacks or stacks
            else:
                # Strip off leading text
                #curLine = curLine[36:]
                inidx = curLine.find(" in ")
                if inidx != -1:
                    curLine = curLine[inidx + 3:]
                # curLine = curLine.replace("mongod!mongo::", "")
                # curLine = curLine.replace("mongod!", "")
                curLine = re_offset.sub("", curLine)
                # print curLine
                cur_stack.append(curLine)



def main():
    parser = argparse.ArgumentParser(description='Process log file.')

    parser.add_argument("files", type=str, nargs='+', help="the file to read" )
    args = parser.parse_args()

    for file in args.files:
        parse_log(file)        



if __name__ == '__main__':
    main()
