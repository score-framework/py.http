# Copyright © 2015-2018 STRG.AT GmbH, Vienna, Austria
# Copyright © 2019 Necdet Can Ateşman, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in the
# file named COPYING.LESSER.txt.
#
# The SCORE Framework and all its parts are distributed without any WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. For more details see the GNU Lesser General Public
# License.
#
# If you have not received a copy of the GNU Lesser General Public License see
# http://www.gnu.org/licenses/.
#
# The License-Agreement realised between you as Licensee and STRG.AT GmbH as
# Licenser including the issue of its valid conclusion and its pre- and
# post-contractual effects is governed by the laws of Austria. Any disputes
# concerning this License-Agreement including the issue of its valid conclusion
# and its pre- and post-contractual effects are exclusively decided by the
# competent court, in whose district STRG.AT GmbH has its registered seat, at
# the discretion of STRG.AT GmbH also the competent court, in whose district the
# Licensee has his registered seat, an establishment or assets.

from score.init import (
    parse_list, parse_dotted_path, extract_conf, parse_bool, ConfigurationError)
import re
from score.init import ConfiguredModule
import inspect
import functools
from ._urltpl import MissingVariable, InvalidVariable
from webob import Request, Response
from webob.exc import (
    HTTPMovedPermanently, HTTPFound, HTTPNotFound, HTTPException,
    HTTPInternalServerError)
import logging
from collections import OrderedDict
import urllib

from ._conf import RouterConfiguration


defaults = {
    'debug': False,
    'preroutes': [],
    'urlbase': None,
    'ctx.member.url': 'url',
    'serve.ip': '0.0.0.0',
    'serve.port': 8080,
    'serve.threaded': False,
}


def init(confdict, ctx, orm=None, tpl=None):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>` with the following configuration keys:

    :confkey:`router`
        Either a path to an instance of :class:`RouteConfiguration` (as
        interpreted by :func:`parse_dotted_path <score.init.parse_dotted_path>`)
        or a list of such paths (as interpreted by :func:`parse_list
        <score.init.parse_list>`).

    :confkey:`preroutes` :confdefault:`list()`
        List of :term:`preroute` functions to call before invoking the actual
        route.  See :ref:`http_routing` for details.

    :confkey:`handler.*`
        Keys starting with "``handler.``" are interpreted as :ref:`error
        handlers <http_error_handler>`.

    :confkey:`debug` :confdefault:`False`
        Setting this to `True` will enable the `werkzeug debugger`_ for your
        application.

    :confkey:`urlbase` :confdefault:`None`
        This will be the prefix for all URLs generated by the module. The module
        will create relative URLs by default (i.e. `/Sir%20Lancelot`), but you
        can make it create absolute URLs by default by paassing this
        configuration value.

        If you configure this to be 'http://example.net/', your URL would be
        'http://example.net/Sir%20Lancelot'.

        Note that you can always decide, whether a *certain* URL should be
        absolute or relative, by passing the appropriate argument to
        :meth:`ConfiguredHttpModule.url`.

    :confkey:`ctx.member.url` :confdefault:`url`
        The name of the :term:`context member` function for generating URLs.

    :confkey:`serve.ip` :confdefault:`0.0.0.0`
        This will be the ip address your HTTP server will bind_ to, when using
        :mod:`score.serve` to serve your application.

    :confkey:`serve.port` :confdefault:`8080`
        This will be the port of your HTTP server, when using
        :mod:`score.serve` to serve your application.

    :confkey:`serve.threaded` :confdefault:`False`
        Setting this to `True` will make your HTTP server threaded, which should
        increase its performance. Note that your application will need to be
        thread-safe_, if you want to enable this feature.

    .. _werkzeug debugger: http://werkzeug.pocoo.org/docs/0.11/debug/#using-the-debugger
    .. _bind: http://www.xeams.com/bindtoaddress.htm
    .. _thread-safe: https://en.wikipedia.org/wiki/Thread_safety
    """
    conf = dict(defaults.items())
    conf.update(confdict)
    if 'router' not in conf:
        import score.http
        raise ConfigurationError(score.http, 'No router provided')
    routers = list(map(parse_dotted_path, parse_list(conf['router'])))
    preroutes = list(map(parse_dotted_path, parse_list(conf['preroutes'])))
    error_handlers = {}
    exception_handlers = {}
    for error, handler in extract_conf(conf, 'handler.').items():
        if re.match('\d(\d\d|XX)', error):
            error_handlers[error] = parse_dotted_path(handler)
        else:
            error = parse_dotted_path(error)
            exception_handlers[error] = handler
    debug = parse_bool(conf['debug'])
    if not conf['urlbase']:
        conf['urlbase'] = ''
    http = ConfiguredHttpModule(
        ctx, orm, tpl, routers, preroutes, error_handlers, exception_handlers,
        debug, conf['urlbase'], conf['serve.ip'], int(conf['serve.port']),
        parse_bool(conf['serve.threaded']))

    def constructor(ctx):
        def url(*args, **kwargs):
            return ctx.http.url(*args, **kwargs)
        return url

    ctx.register(conf['ctx.member.url'], constructor)
    return http


log = logging.getLogger('score.http.router')


class Route:
    """
    A :term:`route` representation.
    """

    def __init__(self, conf, route):
        self.conf = conf
        self.name = route.name
        self.urltpl = route.urltpl
        if isinstance(self.urltpl, str):
            self.urltpl = conf.url_class(self.urltpl)
        self.tpl = route.tpl
        self.callback = route.callback
        self.preconditions = route.preconditions
        self._match2vars = route._match2vars
        self._vars2url = route._vars2url
        self._vars2urlparts = route._vars2urlparts

    @property
    def callback(self):
        return self._callback

    @callback.setter
    def callback(self, callback):
        self._callback = callback
        functools.update_wrapper(self, self.callback)

    def url(self, ctx, *args, **kwargs):
        """
        Creates the URL to this route with given arguments.
        """
        urlbase = ''
        absolute = True
        if '_absolute' in kwargs:
            absolute = kwargs['_absolute']
            del kwargs['_absolute']
            assert '_relative' not in kwargs
        elif '_relative' in kwargs:
            absolute = not kwargs['_relative']
            del kwargs['_relative']
        query = ''
        if '_query' in kwargs:
            if kwargs['_query']:
                query = urllib.parse.urlencode(kwargs['_query'])
            del kwargs['_query']
        anchor = ''
        if '_anchor' in kwargs:
            if kwargs['_anchor']:
                anchor = '#' + urllib.parse.quote(kwargs['_anchor'])
            del kwargs['_anchor']
        if absolute:
            try:
                urlbase = kwargs['_urlbase']
                del kwargs['_urlbase']
            except KeyError:
                urlbase = self.conf.urlbase
        if self._vars2url:
            url = self._vars2url(ctx, *args, **kwargs)
        else:
            if self._vars2urlparts:
                kwargs.update(self._vars2urlparts(ctx, *args, **kwargs))
            self._args2kwargs(args, kwargs)
            variables = self._kwargs2vars(kwargs)
            url = self.urltpl.generate(**variables)
        if urlbase:
            url = urlbase + url
        if query:
            if '?' in url:
                query = '&' + query
            else:
                query = '?' + query
        return url + query + anchor

    def _args2kwargs(self, args, kwargs):
        if not args:
            return
        params = inspect.signature(self.callback).parameters
        for i, name in enumerate(params):
            if name not in kwargs:
                kwargs[name] = args[i - 1]

    def _kwargs2vars(self, kwargs):
        variables = {}
        for name in self.urltpl.variables:
            if name in kwargs:
                variables[name] = kwargs[name]
                continue
            parts = name.split('.')
            if parts[0] not in kwargs:
                raise MissingVariable(parts[0])
            current = kwargs[parts[0]]
            for part in parts[1:]:
                try:
                    current = getattr(current, part)
                except AttributeError:
                    raise InvalidVariable(
                        'Could not retrieve "%s" from %s' %
                        ('.'.join(parts[1:]), kwargs[parts[0]]))
            variables[name] = current
        return variables

    def _call_match2vars(self, ctx, match):
        variables = self.urltpl.match2vars(ctx, match)
        if self._match2vars:
            newvars = self._match2vars(ctx, variables)
            if not newvars:
                log.debug('  %s: registered match2vars() could not '
                          'convert variables (%s)' % (self.name, variables))
                return None
            variables = newvars
        else:
            # remove matches containing dots
            variables = dict((k, v)
                             for (k, v) in variables.items() if '.' not in k)
        for callback in self.preconditions:
            if not callback(ctx, **variables):
                log.debug('  %s: precondition failed (%s)' %
                          (self.name, callback))
                return None
        return variables

    def can_handle(self, request):
        match = self.urltpl.regex.match(urllib.parse.unquote(request.path))
        if not match:
            return False
        ctx = self.conf.ctx.Context()
        ctx.http = self.conf.create_ctx_member(ctx, request)
        try:
            variables = self._call_match2vars(ctx, match)
            if variables is None:
                return False
        except HTTPException:
            # the _match2vars function may raise an HTTPException, which implies
            # that this route would indeed be responsible for the given request,
            # but its implementation chose to handle it prematurely (i.e. before
            # the route callback itself was executed)
            pass
        return True

    def extract_variables(self, request):
        match = self.urltpl.regex.match(urllib.parse.unquote(request.path))
        if not match:
            return None
        ctx = self.conf.ctx.Context()
        ctx.http = self.conf.create_ctx_member(ctx, request)
        try:
            return self._call_match2vars(ctx, match)
        except HTTPException as exception:
            # see can_handle() for the reason we're returning the exception here
            return exception

    def handle(self, ctx):
        request = ctx.http.request
        match = self.urltpl.regex.match(urllib.parse.unquote(request.path))
        if not match:
            log.debug('  %s: No regex match (%s)' %
                      (self.name, self.urltpl.regex.pattern))
            return None
        try:
            variables = self._call_match2vars(ctx, match)
            if variables is None:
                return None
            log.debug('  %s: SUCCESS, invoking callback' % (self.name))
            ctx.http.route = self
            ctx.http.route_vars = variables
            result = self.callback(ctx, **variables)
        except HTTPException as response:
            result = response
        if isinstance(result, Response):
            ctx.http.response = result
            return result
        if isinstance(result, str):
            ctx.http.response.text = result
        elif self.tpl:
            if result is None:
                result = {}
            else:
                assert isinstance(result, dict)
            result['ctx'] = ctx
            ctx.http.response.text = self.conf.tpl.render(self.tpl, result)
        return ctx.http.response


class ConfiguredHttpModule(ConfiguredModule):
    """
    This module's :class:`configuration class <score.init.ConfiguredModule>`.
    """

    def __init__(self, ctx, orm, tpl, routers, preroutes, error_handlers,
                 exception_handlers, debug, urlbase, host, port, threaded):
        self.ctx = ctx
        self.orm = orm
        self.tpl = tpl
        self.routers = routers
        self.router = RouterConfiguration()
        for router in routers:
            self.router.routes.update(router.routes)
        self.preroutes = preroutes
        self.error_handlers = error_handlers
        self.exception_handlers = exception_handlers
        self.debug = debug
        self.urlbase = urlbase
        self.host = host
        self.port = port
        self.threaded = threaded

    def route(self, name):
        """
        Provides the :class:`Route` with given *name*.
        """
        return self.routes[name]

    def newroute(self, *args, **kwargs):
        assert not self._finalized
        return self.router.route(*args, **kwargs)

    def _finalize(self):
        self.routes = OrderedDict((route.name, Route(self, route))
                                  for route in self.router.sorted_routes())
        for name, route in self.routes.items():
            if not route._match2vars and self.orm:
                route._match2vars = self._mk_match2vars(route)
        if not log.isEnabledFor(logging.DEBUG):
            return
        msg = 'Compiled routes:'
        for name, route in self.routes.items():
            msg += '\n - %s (%s)' % (name, route.urltpl)
        log.debug(msg)

    def _mk_match2vars(self, route):
        param2clsid = {}
        parameters = inspect.signature(route.callback).parameters
        test_redirect = False
        for i, (name, param) in enumerate(parameters.items()):
            if i == 0:
                continue
            if param.annotation is inspect.Parameter.empty:
                return
            cls = param.annotation
            if not issubclass(cls, self.orm.Base):
                return
            if ('%s.id' % name) in route.urltpl.variables:
                idcol = 'id'
            else:
                table = cls.__table__
                for var in route.urltpl.variables:
                    match = re.match('%s\.([^.]+)$' % name, var)
                    if not match:
                        continue
                    column_name = match.group(1)
                    column = table.columns.get(column_name)
                    if column is None:
                        parent = cls
                        while parent.__score_sa_orm__['parent']:
                            parent = parent.__score_sa_orm__['parent']
                            column = parent.__table__.columns.get(column_name)
                            if column is not None:
                                break
                        else:
                            import warnings
                            warnings.warn(
                                'Route "%s" references column "%s.%s", '
                                'which does not exist.' % (
                                    route.name, cls.__name__, column_name))
                            return
                    if column.unique:
                        idcol = column_name
                        break
                else:
                    return
            if not test_redirect:
                for var in route.urltpl.variables:
                    if var == '%s.%s' % (name, idcol):
                        continue
                    if var.startswith('%s.' % name):
                        test_redirect = True
                        break
            param2clsid[name] = (cls, idcol)
        if not param2clsid:
            return

        def match2vars(ctx, matches):
            result = {}
            for var, (cls, idcol) in param2clsid.items():
                id = matches['%s.%s' % (var, idcol)]
                result[name] = self.orm.get_session(ctx).query(cls).\
                    filter(getattr(cls, idcol) == id).\
                    first()
                if result[name] is None:
                    return
            if test_redirect and ctx.http.request.method == 'GET':
                realpath = urllib.parse.unquote(
                    route.url(ctx, _relative=True, **result))
                if urllib.parse.unquote(ctx.http.request.path) != realpath:
                    # need to create the url a second time to incorporate the
                    # query string
                    ctx.http.redirect(route.url(
                        ctx, _query=ctx.http.request.GET, **result))
            return result
        return match2vars

    def url(self, ctx, route, *args, **kwargs):
        """
        Shortcut for ``route(route).url(ctx, *args, **kwargs)``.
        """
        return self.route(route).url(ctx, *args, **kwargs)

    def get_serve_runners(self):
        if not hasattr(self, '_serve_runners'):
            import score.serve

            class Runner(score.serve.SocketServerRunner):

                def _mkserver(runner):
                    from werkzeug.serving import make_server
                    return make_server(self.host, self.port, self.mkwsgi(),
                                       threaded=self.threaded)

            self._serve_runners = [Runner()]

        return self._serve_runners

    def score_serve_workers(self):
        if not hasattr(self, '_score_serve_workers'):
            import score.serve
            import socket
            from werkzeug.serving import BaseWSGIServer

            class Server(BaseWSGIServer):
                multithread = self.threaded

                def server_bind(self):
                    self.socket.setsockopt(
                        socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    super().server_bind()

            class Worker(score.serve.SocketServerWorker):

                def _mkserver(runner):
                    return Server(self.host, self.port, self.mkwsgi())

            self._score_serve_workers = Worker()

        return self._score_serve_workers

    def mkwsgi(self):
        """
        Creates a WSGI_ application, that will route incoming requests to the
        configured routes.
        """
        if self.debug:
            def app(env, start_response):
                response = self.create_response(Request(env))
                return response(env, start_response)
            from werkzeug.debug import DebuggedApplication
            app = DebuggedApplication(app, True)
        else:
            def app(env, start_response):
                try:
                    request = Request(env)
                except Exception as e:
                    log.critical(e)
                    response = HTTPInternalServerError()
                else:
                    try:
                        response = self.create_response(request)
                    except Exception as e:
                        log.exception(e)
                        response = self.create_failsafe_response(request, e)
                return response(env, start_response)
        return app

    def find_route_for(self, request_or_url):
        if isinstance(request_or_url, Request):
            request = request_or_url
        else:
            request = Request.blank(request_or_url)
        for route in self.routes.values():
            if route.can_handle(request):
                return route
        return None

    def find_route_and_args_for(self, request_or_url):
        if isinstance(request_or_url, Request):
            request = request_or_url
        else:
            request = Request.blank(request_or_url)
        for route in self.routes.values():
            result = route.extract_variables(request)
            if result is not None:
                return route, result
        return None, None

    def create_ctx_member(self, ctx, request):
        return Http(self, ctx, request)

    def create_response(self, request):
        ctx = self.ctx.Context()
        ctx.http = self.create_ctx_member(ctx, request)
        try:
            log.debug('Received %s request for %s' %
                      (request.method, request.path))
            result = None
            try:
                for preroute in self.preroutes:
                    result = preroute(ctx)
                    if isinstance(result, Response):
                        break
            except HTTPException as response:
                result = response
            if isinstance(result, Response):
                ctx.http.response = result
            else:
                for name, route in self.routes.items():
                    if route.handle(ctx):
                        break
                else:
                    ctx.http.response = self.create_error_response(
                        ctx, HTTPNotFound())
        except Exception as e:
            for exc in self.exception_handlers:
                # let's see if we have a dedicated exception handler for this
                # kind of error
                if isinstance(e, exc):
                    try:
                        self.exception_handlers[exc](ctx, e)
                        break
                    except HTTPException as response:
                        ctx.http.response = response
                        break
                    except Exception as e2:
                        ctx.destroy(e2)
                        raise
            else:
                ctx.destroy(e)
                raise
        response = ctx.http.response
        ctx.destroy()
        return response

    def create_failsafe_response(self, request, error=None):
        try:
            with self.ctx.Context() as ctx:
                ctx.tx.doom()
                ctx.http = Http(self, ctx, request)
                ctx.http.exc = ctx.http.exception = error
                response = self.create_error_response(ctx, error)
                return response
        except Exception as e:
            if ctx._active:
                try:
                    ctx.destroy(e)
                except Exception:
                    log.exception(e)
                    pass
            log.critical(e)
            return HTTPInternalServerError()
        finally:
            assert not ctx or not ctx._active

    def create_error_response(self, ctx, error):
        code = 500
        if isinstance(error, HTTPException):
            code = error.code
            ctx.http.response = ctx.http.res = error
        else:
            ctx.http.response = ctx.http.res = HTTPInternalServerError()
        handler = None
        if str(code) in self.error_handlers:
            handler = self.error_handlers[str(code)]
        elif '%dXX' % (code % 100) in self.error_handlers:
            handler = self.error_handlers['%dXX' % (code % 100)]
        if not handler:
            return ctx.http.response
        try:
            result = handler(ctx, error)
        except HTTPException as response:
            result = response
        if isinstance(result, Response):
            ctx.http.response = result
            return result
        if isinstance(result, str):
            ctx.http.response.text = result
        return ctx.http.response


class Http:

    def __init__(self, conf, ctx, request):
        self._conf = conf
        self._ctx = ctx
        self._response = None
        self.req = self.request = request
        self.urlbase = None

    def redirect(self, url, permanent=False, *, merge_cookies=True):
        if not permanent:
            exc = HTTPFound(location=url)
        else:
            exc = HTTPMovedPermanently(location=url)
        if merge_cookies and self._response:
            exc.merge_cookies(self._response)
        raise exc

    @property
    def response(self):
        if self._response is None:
            self._response = Response(conditional_response=True)
            self._response.charset = 'utf-8'
        return self._response

    @response.setter
    def response(self, value):
        self._response = value

    def url(self, *args, **kwargs):
        if '_urlbase' not in kwargs and self.urlbase:
            kwargs['_urlbase'] = self.urlbase
        return self._conf.url(self._ctx, *args, **kwargs)

    res = response
