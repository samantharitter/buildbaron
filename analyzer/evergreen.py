"""
Classes and utility functions for accessing evergreen
"""
import yaml
import os.path
import requests
from . import analyzer_config

class client(object):
    """HTTP client for evergreen api that uses users's Evergreen key"""
    def __init__(self, **kwargs):
        self.user, self.api_key = self._read_config()

        return super().__init__(**kwargs)

    def _read_config(self, file = None):
        if file is None:
            file = analyzer_config.evergreen_config_default_file()

        with open(file, "rb") as sjh:
            contents = sjh.read().decode('utf-8')
            config = yaml.safe_load(contents)

        user = config['user']
        api_key = config['api_key']
        return user, api_key

    def retrieve_file(self, url, file):
        print("Retrieving: " + url);
            
        headers = {'Auth-Username': self.user, 
                   'Api-Key': self.api_key}

        r = requests.get(url, headers=headers)

        with open(file, "wb") as lfh:
            lfh.write(r.content)



def append_iteration_suffix(task_url):
    """ tasks can have multiple iteratons, assume the first unless otherwise specified"""
    if not task_url.endswith('/0'):
        return task_url + '/0'
    return task_url

def task_get_task_raw_log(task_url):
    """Get the task log for the evergreen task"""
    log_file_url = append_iteration_suffix(task_url) + "?type=T&text=true";
    return log_file_url.replace("task", "task_log_raw");

def task_get_system_raw_log(task_url):
    """Get the task log for the evergreen task system log"""
    log_file_url = append_iteration_suffix(task_url) + "?type=S&text=true";
    return log_file_url.replace("task", "task_log_raw");

# Example: https://evergreen.mongodb.com/task/<task_id>
def get_task_id_from_task_url(task_url):
    pred = "task/"
    idx = task_url.find(pred)
    return task_url[idx + len(pred)]