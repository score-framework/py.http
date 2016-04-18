# Copyright © 2015 STRG.AT GmbH, Vienna, Austria
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
    HTTPRedirection, HTTPOk, HTTPInternalServerError)
import logging
from collections import OrderedDict
import urllib


defaults = {
    'debug': False,
    'preroutes': [],
    'urlbase': None,
    'host': '0.0.0.0',
    'port': 8080,
    'threaded': False,
}


def init(confdict, ctx, db=None):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>` with the following configuration keys:

    :confkey:`router`
        Path to the :class:`RouteConfiguration` containing the list of routes to
        compile.

    :confkey:`preroutes`
        List of :term:`preroute` functions to call before invoking the actual
        route.  See :ref:`http_routing` for details.

    :confkey:`handler.*`
        TODO: document me

    :confkey:`debug` :default:`False`
        TODO: document me

    :confkey:`urlbase`
        TODO: document me

    :confkey:`host`
        TODO: document me

    :confkey:`port`
        TODO: document me

    :confkey:`threaded`
        TODO: document me
    """
    conf = dict(defaults.items())
    conf.update(confdict)
    if 'router' not in conf:
        import score.http
        raise ConfigurationError(score.http, 'No router provided')
    router = parse_dotted_path(conf['router'])
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
        ctx, db, router, preroutes, error_handlers, exception_handlers, debug,
        conf['urlbase'], conf['host'], int(conf['port']),
        parse_bool(conf['threaded']))

    def constructor(ctx):
        def url(*args, **kwargs):
            return http.url(ctx, *args, **kwargs)
        return url

    ctx.register('url', constructor)
    return http


log = logging.getLogger('score.http.router')


class Route:

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
                query = '?' + urllib.parse.urlencode(kwargs['_query'])
            del kwargs['_query']
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
        return url + query

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
            for preroute in self.conf.preroutes:
                preroute(ctx)
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
            ctx.http.response.text = self.conf.tpl.renderer.render_file(
                ctx, self.tpl, result)
        return ctx.http.response


class ConfiguredHttpModule(ConfiguredModule):

    def __init__(self, ctx, db, router, preroutes, error_handlers,
                 exception_handlers, debug, urlbase, host, port, threaded):
        self.ctx = ctx
        self.db = db
        self.router = router.clone()
        self.preroutes = preroutes
        self.error_handlers = error_handlers
        self.exception_handlers = exception_handlers
        self.debug = debug
        self.urlbase = urlbase
        self.host = host
        self.port = port
        self.threaded = threaded

    def route(self, name):
        return self.routes[name]

    def newroute(self, *args, **kwargs):
        assert not self._finalized
        return self.router.route(*args, **kwargs)

    def _finalize(self, db=None, tpl=None):
        self.tpl = tpl
        self.routes = OrderedDict((route.name, Route(self, route))
                                  for route in self.router.sorted_routes())
        for name, route in self.routes.items():
            if not route._match2vars and db:
                route._match2vars = self._mk_match2vars(route)
        if not log.isEnabledFor(logging.INFO):
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
            if not issubclass(cls, self.db.Base):
                return
            if ('%s.id' % name) in route.urltpl.variables:
                idcol = 'id'
            else:
                table = cls.__table__
                for var in route.urltpl.variables:
                    match = re.match('%s\.([^.]+)$' % name, var)
                    if not match:
                        continue
                    col = match.group(1)
                    # TODO: handle the case where the column is part of a parent
                    # table
                    if table.columns.get(col).unique:
                        idcol = col
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
                result[name] = ctx.db.query(cls).\
                    filter(getattr(cls, idcol) == id).\
                    first()
                if result[name] is None:
                    return
            if test_redirect and ctx.http.request.method == 'GET':
                realpath = route.url(ctx, _relative=True, **result)
                if ctx.http.request.path != realpath:
                    # need to create the url a second time to incorporate the
                    # query string
                    ctx.http.redirect(route.url(
                        ctx, _query=ctx.http.request.GET, **result))
            return result
        return match2vars

    def url(self, ctx, route, *args, **kwargs):
        """
        Shortcut for ``route(route).url(*args, **kwargs)``.
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

    def mkwsgi(self):
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

    def create_ctx_member(self, request):
        return Http(self, request)

    def create_response(self, request):
        ctx = self.ctx.Context()
        ctx.http = self.create_ctx_member(request)
        try:
            log.debug('Received %s request for %s' %
                      (request.method, request.path))
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
                        self.exception_handlers[exc](ctx)
                        break
                    except (HTTPOk, HTTPRedirection) as success:
                        ctx.http.response = success
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
                ctx.http = Http(self, request)
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

    def __init__(self, conf, request):
        self._conf = conf
        self._response = None
        self.req = self.request = request
        self.url = conf.url

    def redirect(self, url, permanent=False):
        if not permanent:
            raise HTTPFound(location=url)
        else:
            raise HTTPMovedPermanently(location=url)

    @property
    def response(self):
        if self._response is None:
            self._response = Response(conditional_response=True)
            self._response.charset = 'utf8'
        return self._response

    @response.setter
    def response(self, value):
        self._response = value

    res = response
