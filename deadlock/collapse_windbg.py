import argparse
import os
import re
import string
import subprocess

parser = argparse.ArgumentParser(description='Dedup windbg stacks')
parser.add_argument('file', type=argparse.FileType('r'), help='file to read')

args = parser.parse_args()

diff_file = args.file.name

file = open(diff_file, "r")

in_stack = 0
cur_stack = []
stack_num = 0

stacks = []
re_offset = re.compile("\+0x[0-9a-fA-F]+")
while True:
    curLine = file.readline()
    if(curLine == ""):
        break
    curLine = curLine.rstrip().lstrip()

    # TODO: strip off [dates and times]

    #print "%d, %s" % (in_stack, curLine)
    # Ignore comments
    if(curLine.startswith("//")):
        continue
    elif(curLine.startswith("***")):
        continue
    elif curLine.startswith("Child-SP"):
        #New Stack
        # cur_stack.reverse()
        #print "stck"
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

stacks_set = set(stacks)

print "Unique stacks: " + str(len(stacks_set))

for stack in stacks_set:
    print "--------------"
    print "\n".join(string.split(stack, ";"))
