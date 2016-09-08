import sys
import os
import json
from git import Repo


if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(os.path.realpath(__file__)))))
    print (sys.path)

#from buildbaron.www import analyzer
#import buildbaron.analyzer
#from buildbaron import analyzer
import buildbaron.analyzer.evergreen_analyzer

def get_changes(repo_dir):
    repo = Repo(repo_dir)

    assert not repo.bare

    origin = repo.remotes.origin

    print("Updaing origin")
    origin.fetch()

    master = origin.refs.master

    commits = []
    for c in repo.iter_commits(master, since="yesterday"):
        commits.append(str(c))

    return commits;


def main():
    first = False


    if first:

        versions_url = "https://evergreen.mongodb.com/rest/v1/projects/mongodb-mongo-master/versions"

        failed_tests = buildbaron.analyzer.evergreen_analyzer.get_failed_test_info(versions_url)
    else:
        commits = get_changes("d:\\m2\mongo")
   
        failed_tests = buildbaron.analyzer.evergreen_analyzer.get_failed_test_info_by_commits("https://evergreen.mongodb.com/", commits)

    with open("failed_tests.json", "w", encoding="utf8") as sjh:
        json.dump(failed_tests, sjh, indent="\t")

if __name__ == '__main__':
    main()