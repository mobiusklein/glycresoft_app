import re
import logging
from typing import Callable, Union

import waitress

from flask import request, Flask
from werkzeug.serving import run_simple
from werkzeug.wsgi import LimitedStream

logger = logging.getLogger("glycresoft")

class StreamConsumingMiddleware(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        stream = LimitedStream(environ['wsgi.input'],
                               int(environ.get('CONTENT_LENGTH') or 0))
        environ['wsgi.input'] = stream
        app_iter = self.app(environ, start_response)
        try:
            stream.exhaust()
            for event in app_iter:
                yield event
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()


class LoggingMiddleware(object):
    def __init__(self, app, logger=logger):
        self.app = app
        self.logger = logger

    def make_start_response(self, start_response, url):
        def wrapper(status, response_headers):
            self.logger.info(f": {url} -> {status}")
            return start_response(status, response_headers)

        return wrapper

    def __call__(self, environ, start_response):
        url = environ['PATH_INFO']
        self.logger.debug(f": Starting {url}")
        return self.app(environ, self.make_start_response(start_response, url))

class AddressFilteringMiddleware(object):
    def __init__(self, app, blacklist=None, whitelist=None):
        if blacklist is None:
            blacklist = []
        if whitelist is None:
            whitelist = []
        self.app = app
        self.blacklist = []
        self.whitelist = []

        for item in blacklist:
            self.add_address_to_filter(item)

        for item in whitelist:
            self.add_address_to_allow(item)

    def __call__(self, environ, start_response):
        client_ip = environ['REMOTE_ADDR']
        for pattern in self.whitelist:
            if pattern.match(client_ip):
                return self.app(environ, start_response)
        for pattern in self.blacklist:
            if pattern.match(client_ip):
                start_response("403", {})
                return iter(("Connection Refused!",))
        else:
            return self.app(environ, start_response)

    def add_address_to_filter(self, ipaddr):
        pattern = re.compile(ipaddr)
        self.blacklist.append(pattern)

    def add_address_to_allow(self, ipaddr):
        pattern = re.compile(ipaddr)
        self.whitelist.append(pattern)


class AddressFilteringApplication(object):
    def __init__(self, app, blacklist=None, whitelist=None):
        if blacklist is None:
            blacklist = []
        if whitelist is None:
            whitelist = []
        self.app = app
        self._whitelist = list(whitelist)
        self._blacklist = list(blacklist)
        self._filter = AddressFilteringMiddleware(
            self.app.wsgi_app, self._blacklist, self._whitelist)
        self.app.wsgi_app = self._filter

    def blacklist(self, ipaddr):
        self._filter.add_address_to_filter(ipaddr)

    def whitelist(self, ipaddr):
        self._filter.add_address_to_allow(ipaddr)


class ApplicationServer(object):
    app: Flask
    port: Union[int, str]
    host: str
    debug: bool

    shutdown: Callable[[], None]

    def __init__(self, app, port, host, debug):
        self.app = app
        self.port = port
        self.host = host
        self.debug = debug

    def shutdown_server(self):
        self.shutdown()


class ApplicationServerManager(object):
    pass


class WerkzeugApplicationServer(ApplicationServer):
    def __init__(self, app, port, host, debug):
        super(WerkzeugApplicationServer, self).__init__(app, port, host, debug)

    def shutdown(self):
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')

        func()

    def run(self):
        run_simple(
            hostname=self.host, port=self.port, application=self.app,
            threaded=True, use_debugger=self.debug, use_reloader=False,
            passthrough_errors=True)


ApplicationServerManager.werkzeug_server = WerkzeugApplicationServer

class WaitressApplicationServer(ApplicationServer):
    def __init__(self, app, port, host, debug):
        super().__init__(LoggingMiddleware(app), port, host, debug)
        self.server = None

    def shutdown(self):
        logger.info(f"Stopping application server on  {self.host}:{self.port}")
        if self.server is not None:
            self.server.close()
            logger.info(
                "Stopped application server")

    def run(self):
        logger.info(f"Starting application server on  {self.host}:{self.port}")
        self.server = waitress.create_server(self.app, host=self.host, port=self.port, )
        self.server.run()


ApplicationServerManager.waitress_server = WaitressApplicationServer
