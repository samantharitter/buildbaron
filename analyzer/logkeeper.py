"""API for accessing logkeeper files

See https://github.com/evergreen-ci/logkeeper
"""
import requests

def retrieve_file(url, file):
    print("Retrieving: " + url);

    r = requests.get(url)
    with open(file, "wb") as lfh:
        lfh.write(r.content)

def get_raw_log_url(url):
    if "?" in url:
        raise ValueError("Wrong URL since it already contains a parameter: %s " % url)

    return url + "?raw=1"

def retieve_raw_log(url, file):
    url = get_raw_log_url(url)

    retrieve_file(url, file)