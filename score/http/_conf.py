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

from score.init import ConfiguredModule
import inspect
import functools
from .url import MissingVariable, InvalidVariable
from webob import Request, Response
from webob.exc import (
    HTTPMovedPermanently, HTTPFound, HTTPNotFound, HTTPException,
    HTTPRedirection, HTTPOk, HTTPInternalServerError)
import logging
from collections import OrderedDict
import urllib

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
        if self._vars2url:
            return self._vars2url(ctx, *args, **kwargs)
        if self._vars2urlparts:
            kwargs.update(self._vars2urlparts(*args, **kwargs))
        self._args2kwargs(args, kwargs)
        variables = self._kwargs2vars(kwargs)
        url = self.urltpl.generate(**variables)
        if '_query' in kwargs:
            url += '?' + urllib.parse.urlencode(kwargs['_query'])
        return url

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

    def handle(self, ctx):
        match = self.urltpl.regex.match(ctx.http.request.path)
        if not match:
            log.debug('  %s: No regex match (%s)' %
                      (self.name, self.urltpl.regex.pattern))
            return None
        variables = self.urltpl.match2vars(ctx, match)
        if self._match2vars:
            newvars = self._match2vars(ctx, variables)
            if not newvars:
                log.debug('  %s: registered match2vars() could not '
                          'convert variables (%s)' % (self.name, variables))
                return None
            variables = newvars
        for callback in self.preconditions:
            if not callback(ctx, **variables):
                log.debug('  %s: precondition failed (%s)' %
                          (self.name, callback))
                return None
        result = self.callback(ctx, **variables)
        log.debug('  %s: SUCCESS' % (self.name))
        if isinstance(result, Response):
            return result
        if isinstance(result, str):
            ctx.http.response.text = result
        elif self.tpl:
            if result is None:
                result = {}
            assert isinstance(result, dict)
            result['ctx'] = ctx
            ctx.http.response.text = ctx.conf.tpl.renderer.render_file(
                ctx, self.tpl, result)
        return ctx.http.response


class ConfiguredHttpModule(ConfiguredModule):

    def __init__(self, ctx, db, router, error_handlers,
                 exception_handlers, debug):
        self.ctx = ctx
        self.db = db
        self.router = router.clone()
        self.error_handlers = error_handlers
        self.exception_handlers = exception_handlers
        self.debug = debug

    def route(self, name):
        return self.routes[name]

    def newroute(self, *args, **kwargs):
        assert not self._finalized
        return self.router.route(*args, **kwargs)

    def _finalize(self, db=None):
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
        log.info(msg)

    def _mk_match2vars(self, route):
        param2cls = {}
        parameters = inspect.signature(route.callback).parameters
        for i, (name, param) in enumerate(parameters.items()):
            if i == 0:
                continue
            if param.annotation is inspect.Parameter.empty:
                return
            if ('%s.id' % name) not in route.urltpl.variables:
                # TODO: we could also test for other members in the variables
                # list, that access a column with a unique-constraint.
                return
            param2cls[name] = param.annotation
        if not param2cls:
            return

        def loader(ctx, matches):
            result = {}
            for var, cls in param2cls.items():
                result[name] = ctx.db.query(cls).get(matches['%s.id' % var])
                if result[name] is None:
                    return
            return result
        return loader

    def url(self, ctx, route, *args, **kwargs):
        """
        Shortcut for ``route(route).url(*args, **kwargs)``.
        """
        return self.route(route).url(ctx, *args, **kwargs)

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
        except (HTTPOk, HTTPRedirection) as success:
            ctx.http.response = success
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
        handler = None
        if code in self.error_handlers:
            handler = self.error_handlers[code]
        elif '%dXX' % (code % 100) in self.error_handlers:
            handler = self.error_handlers['%dXX' % (code % 100)]
        if not handler:
            if isinstance(error, HTTPException):
                return error
            return HTTPInternalServerError()
        return handler(ctx, error)


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
