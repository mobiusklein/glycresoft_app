from flask import Blueprint

services = []


def register_service(*args, **kwargs):
    blueprint = Blueprint(*args, **kwargs)
    services.append(blueprint)
    return blueprint


def load_all_services(app):
    for service in services:
        app.register_blueprint(service)
    return app
