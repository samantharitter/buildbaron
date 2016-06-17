import sys
import os
import json

if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__)))))
    print sys.path

#from buildbaron.www import analyzer
#import buildbaron.analyzer
from buildbaron import analyzer

print dir(analyzer)

def main():
    versions_url = "https://evergreen.mongodb.com/rest/v1/projects/mongodb-mongo-master/versions"

    failed_tests = analyzer.evergreen_analyzer.get_failed_test_info(versions_url)
   
    with open("failed_tests.json", "wb") as sjh:
        json.dump(failed_tests, sjh)

if __name__ == '__main__':
    main()