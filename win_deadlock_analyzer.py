#!/usr/bin/env python3
import argparse
import json
import os
import pprint
import re
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
    print("Staring Analysis")

    while True:
        curLine = file.readline()
        if curLine == "":
            break
        curLine = curLine.rstrip().lstrip()

        if not in_dbg:
            if "Windows Debugger" not in curLine:
                continue

        # Found start of debuggers
        in_dbg = 1

        if "Done analyzing process" in curLine:
            # Done With Debuggers
            in_dbg = 0

        # Strip Date Prefix
        curLine = re_files.sub("", curLine)

        if curLine.startswith("***"):
            continue
        elif curLine.startswith("   0  Id: "):
            # Stacks start
            in_stacks = 1
        elif curLine.startswith("Creating dump"):
            # Stacks end
            in_stacks = 0

            # Summarize
            stack_map = {}
            for stack in stacks:
                if stack not in stack_map:
                    stack_map[stack] = 0
                stack_map[stack] = stack_map[stack] + 1

            print("======================================")
            print("--------------------------------------")
            print("Unique stacks: " + str(len(stack_map)) + " of ") + str(len(stacks))
            print("======================================")

            for stack in stack_map:
                print("-------------- Count: %d") % (stack_map[stack])
                print("\n".join(string.split(stack, ";")))

            stacks = []

        if in_stacks:
            if curLine.startswith("Child-SP"):
                #New Stack
                # cur_stack.reverse()
                #print("stck")
                stack_str = string.join(cur_stack, ";")
                stacks.append(stack_str)

                cur_stack = []
                continue
            # Ignore blank lines, they separate allocations from stacks or stacks
            elif "  Id" in curLine:
                #New Stack
                continue
            else:
                # Strip off leading text
                curLine = curLine[36:]
                # curLine = curLine.replace("mongod!mongo::", "")
                # curLine = curLine.replace("mongod!", "")
                curLine = re_offset.sub("", curLine)
                # print curLine
                cur_stack.append(curLine)


def main():
    parser = argparse.ArgumentParser(description='Process log file.')

    parser.add_argument("files", type=str, nargs='+', help="the file to read")
    args = parser.parse_args()

    for file in args.files:
        parse_log(file)


if __name__ == '__main__':
    main()
