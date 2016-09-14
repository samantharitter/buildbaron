from jira import JIRA
import os
import re
import argparse
import pprint
import json
import getpass

try:
  import keyring
except ImportError:
  keyring = None


# URL of the default Jira server.
DEFAULT_JIRA_SERVER = "https://jira.mongodb.com"

class jira_analyzer(object):
    """description of class"""
    def __init__(self, jira_server, jira_user):

        self.jira = JIRA(server=jira_server, options={'verify' : False}, basic_auth=(jira_user, jira_analyzer._get_password(jira_server, jira_user ))) 

    @staticmethod
    def _get_password(server, user):
      global keyring

      password = None
      
      if keyring:
        try:
          password = keyring.get_password(server, user)
        except:
          print("Failed to get password from keyring")
          keyring = None
 
      if password is not None:
        print("Using password from system keyring.")
      else:
        password = getpass.getpass("Jira Password:")
 
        if keyring:
          answer = raw_input("Store password in system keyring? (y/N): ").strip()
 
          if answer == "y":
            keyring.set_password(server, user, password)
 
      return password

    def query(self, fields):
        # my top 5 issues due by the end of the week, ordered by priority
        search = " or ".join([ 'text~"%s"' % f for f in fields])

        results = self.jira.search_issues(search)


        # TODO get fields

        print(len(results))

        return results

    def compute_likelyhood(results):
        return 0.1;

def main():
    parser = argparse.ArgumentParser(description='Analyze test failure in jira.')

    
    group = parser.add_argument_group("Jira options")
    group.add_argument('--jira_server', type=str, help="Jira Server to query",
                       default=DEFAULT_JIRA_SERVER)
    group.add_argument('--jira_user', type=str, help="Jira user name", default=None)

    parser.add_argument("terms", type=str, nargs='+', help="the file to read" )


    args = parser.parse_args()

    try:

        ja = jira_analyzer(args.jira_server, args.jira_user)

        ja.query(args.terms)

    except Exception  as e:
        print("Exception:" + str(e))
                

if __name__ == '__main__':
    main()
