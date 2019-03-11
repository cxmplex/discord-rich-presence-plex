import json


def get_configs():
    with open('config.json') as f:
        data = json.load(f)
        return data
