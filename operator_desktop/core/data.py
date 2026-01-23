import json


DEFAULT_CLIENTS = [
    {
        "id": "RC-2031",
        "name": "PC-RC-2031",
        "region": "region_eu",
        "ip": "192.168.32.10",
        "connected": False,
        "status": "connected",
        "connected_time": 0,
        "assigned_operator_id": "OP-1002",
    },
    {
        "id": "RC-1184",
        "name": "PC-RC-1184",
        "region": "region_na",
        "ip": "10.0.5.77",
        "connected": False,
        "status": "disconnected",
        "connected_time": 0,
        "assigned_operator_id": "OP-1001",
    },
    {
        "id": "RC-3920",
        "name": "PC-RC-3920",
        "region": "region_apac",
        "ip": "172.16.4.18",
        "connected": False,
        "status": "disconnected",
        "connected_time": 0,
        "assigned_operator_id": "OP-2002",
    },
    {
        "id": "RC-4420",
        "name": "PC-RC-4420",
        "region": "region_sa",
        "ip": "192.168.12.54",
        "connected": False,
        "status": "connected",
        "connected_time": 0,
        "assigned_operator_id": "OP-2001",
    },
]

DEFAULT_TEAMS = [
    {
        "id": "TEAM-01",
        "name": "Northline Support",
        "activity": True,
        "subscription_end": "2025-12-31",
        "members": [
            {
                "name": "Avery Grant",
                "tag": "administrator",
                "account_id": "OP-1001",
                "password": "Passw0rd!",
            },
            {
                "name": "Leo Martinez",
                "tag": "operator",
                "account_id": "OP-1002",
                "password": "Passw0rd!",
            },
            {
                "name": "Mia Chen",
                "tag": "moderator",
                "account_id": "MOD-2001",
                "password": "Passw0rd!",
            },
        ],
    },
    {
        "id": "TEAM-02",
        "name": "Atlas Helpdesk",
        "activity": True,
        "subscription_end": "2025-10-15",
        "members": [
            {
                "name": "Nora Patel",
                "tag": "administrator",
                "account_id": "OP-2001",
                "password": "Passw0rd!",
            },
            {
                "name": "Ivan Volkov",
                "tag": "operator",
                "account_id": "OP-2002",
                "password": "Passw0rd!",
            },
        ],
    },
]

DEFAULT_OPERATORS = [
    {
        "id": "OP-1001",
        "name": "Avery Grant",
        "password": "Passw0rd!",
        "role": "administrator",
        "team": "TEAM-01",
    },
    {
        "id": "OP-1002",
        "name": "Leo Martinez",
        "password": "Passw0rd!",
        "role": "operator",
        "team": "TEAM-01",
    },
    {
        "id": "MOD-2001",
        "name": "Mia Chen",
        "password": "Passw0rd!",
        "role": "moderator",
        "team": "TEAM-01",
    },
    {
        "id": "OP-2001",
        "name": "Nora Patel",
        "password": "Passw0rd!",
        "role": "administrator",
        "team": "TEAM-02",
    },
    {
        "id": "OP-2002",
        "name": "Ivan Volkov",
        "password": "Passw0rd!",
        "role": "operator",
        "team": "TEAM-02",
    },
]

DEFAULT_SETTINGS = {
    "theme": "dark",
    "language": "en",
    "role": "operator",
    "remember_me": False,
    "account_id": "",
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
        "output_dir": "",
        "icon_path": "",
        "mode": "onefile",
        "console": "hide",
    },
}


def deep_copy(value):
    return json.loads(json.dumps(value))
