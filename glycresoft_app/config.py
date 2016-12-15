import os
try:
    from ConfigParser import ConfigParser
except:
    from configparser import ConfigParser


default_config = {
    "WebServer": {
        "HealthCheckInterval": 10000,
        "AllowExternalConnections": False,
    },
    "Database": {
        "RemoteAddress": None,
    },
    "TaskHandling": {
        "RefreshTaskInterval": 25000,
    }
}


def _make_parser_with_defaults():
    parser = ConfigParser()
    for section, options in default_config.items():
        parser.add_section(section)
        for name, value in options.items():
            parser.set(section, name, value)
    return parser


def get(path):
    parser = _make_parser_with_defaults()
    if os.path.exists(path):
        parser.read([path])
        config_dict = {
            "allow_external_connections": parser.getboolean("WebServer", "AllowExternalConnections"),
            "refresh_task_interval": parser.getint("TaskHandling", "RefreshTaskInterval"),
            "upkeep_interval": parser.getint("WebServer", "HealthCheckInterval")
        }
        return config_dict
    else:
        parser.write(open(path, 'w'))
        return get(path)
