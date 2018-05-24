import os
try:
    from ConfigParser import SafeConfigParser as ConfigParser
except ImportError:
    from configparser import SafeConfigParser as ConfigParser

from collections import defaultdict


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
    },
    "Performance": {
        "PreprocessorWorkerCount": 5,
        "DatabaseBuildWorkerCount": 4,
        "DatabaseSearchWorkerCount": 5,
    }
}


def _make_parser_with_defaults():
    parser = ConfigParser()
    parser.optionxform = str
    for section, options in default_config.items():
        parser.add_section(section)
        for name, value in options.items():
            # If a value is missing from the file and
            # must be parsed from the defaults, the
            # value must be stored as a string for the
            # type parsing facilities to not error out.
            parser.set(section, name, str(value))
    return parser


def deduplicate(parser):
    for section in list(parser.sections()):
        items = {}
        forms = defaultdict(list)
        for key, value in parser.items(section):
            forms[key.lower()].append(key)
            items[key.lower()] = value
        deduplicated = {}
        for key, key_forms in forms.items():
            if len(key_forms) == 1:
                deduplicated[key_forms[0]] = items[key]
            else:
                key_forms = [key_form for key_form in key_forms if key_form != key]
                if not key_forms:
                    deduplicated[key] = items[key]
                else:
                    deduplicated[key_forms[0]] = items[key]
        parser.remove_section(section)
        parser.add_section(section)
        for key, value in deduplicated.items():
            parser.set(section, key, str(value))
    return parser


def write(config_dict, path):
    converted = {
        "WebServer": {
            "AllowExternalConnections": str(config_dict['allow_external_connections']),
            "HealthCheckInterval": str(config_dict['upkeep_interval']),
        },
        "TaskHandling": {
            "RefreshTaskInterval": str(config_dict["refresh_task_interval"]),
        },
        "Performance": {
            "PreprocessorWorkerCount": str(config_dict['preprocessor_worker_count']),
            "DatabaseBuildWorkerCount": str(config_dict['database_build_worker_count']),
            "DatabaseSearchWorkerCount": str(config_dict['database_search_worker_count'])
        }
    }
    parser = ConfigParser()
    parser.optionxform = str
    for section, options in converted.items():
        parser.add_section(section)
        for name, value in options.items():
            # If a value is missing from the file and
            # must be parsed from the defaults, the
            # value must be stored as a string for the
            # type parsing facilities to not error out.
            parser.set(section, name, str(value))
    parser.write(open(path, 'w'))


def get_parser(path):
    parser = _make_parser_with_defaults()
    if os.path.exists(path):
        parser.read([path])
    deduplicate(parser)
    return parser


def make_parser_from_ini_dict(config):
    parser = ConfigParser()
    parser.optionxform = str
    for section, options in config.items():
        parser.add_section(section)
        for key, value in options.items():
            parser.set(section, key, str(value))
    return parser


def convert_parser_to_config_dict(parser):
    config_dict = {
        "allow_external_connections": parser.getboolean("WebServer", "AllowExternalConnections"),
        "refresh_task_interval": parser.getint("TaskHandling", "RefreshTaskInterval"),
        "upkeep_interval": parser.getint("WebServer", "HealthCheckInterval"),
    }
    config_dict.update({
        "preprocessor_worker_count": parser.getint("Performance", "PreprocessorWorkerCount"),
        "database_build_worker_count": parser.getint("Performance", "DatabaseBuildWorkerCount"),
        "database_search_worker_count": parser.getint("Performance", "DatabaseSearchWorkerCount")
    })
    return config_dict


def get(path):
    parser = _make_parser_with_defaults()
    if os.path.exists(path):
        parser.read([path])
        deduplicate(parser)
        config_dict = convert_parser_to_config_dict(parser)
        return config_dict
    else:
        deduplicate(parser)
        parser.write(open(path, 'w'))
        return get(path)
