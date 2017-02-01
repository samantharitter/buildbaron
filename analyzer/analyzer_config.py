import os

import yaml

DEFAULT_JIRA_SERVER = "https://jira.mongodb.org"
DEFAULT_BB_CONFIG = "~/.buildbaron.yaml"

def jira_server():
    return DEFAULT_JIRA_SERVER

def jira_user():
    if os.getenv("JIRA_USER_NAME") is not None:
        return os.getenv("JIRA_USER_NAME")

    file = os.path.expanduser(DEFAULT_BB_CONFIG)
    if os.path.exists(file):
        with open(file, "rb") as sjh:
            contents = sjh.read().decode('utf-8') 
            config = yaml.safe_load(contents)

        user = config['user']
        return user
    
    raise ValueError("Jira user cannot be determined, please set the environment variable JIRA_USER_NAME or put a 'user' field in '%s'" % file);

def evergreen_config_default_file():
    return os.path.expanduser("~/.evergreen.yml")
