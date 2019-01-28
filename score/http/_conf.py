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

from ._urltpl import UrlTemplate, PatternUrlTemplate
from score.init import (
    InitializationError as ScoreInitializationError,
    DependencySolver, DependencyLoop as ScoreInitDependencyLoop)
from itertools import permutations
import functools
import os
import mimetypes
from webob.exc import HTTPNotFound


class InitializationError(ScoreInitializationError):

    def __init__(self, msg):
        import score.http
        super().__init__(score.http, msg)


class DependencyLoop(InitializationError):

    def __init__(self, loop):
        super().__init__('Cannot resolve ordering of the following routes:\n' +
                         '\n'.join(map(lambda x: ' - ' + x, loop)))


class DuplicateRouteDefinition(InitializationError):

    def __init__(self, route_name, *args, **kwargs):
        self.route_name = route_name
        super().__init__(
            'Route "%s" already defined' % route_name, *args, **kwargs)


class RouteConfiguration:

    def __init__(self, name, urltpl, tpl, callback):
        self.name = name
        self.urltpl = urltpl
        self.tpl = tpl
        self.callback = callback
        self.preconditions = []
        self._match2vars = None
        self._vars2url = None
        self._vars2urlparts = None
        self.before = []
        self.after = []

    @property
    def callback(self):
        return self._callback

    @callback.setter
    def callback(self, callback):
        self._callback = callback
        functools.update_wrapper(self, self.callback)

    def __call__(self, *args, **kwargs):
        return self.callback(*args, **kwargs)

    def precondition(self, func):
        self.preconditions.append(func)
        return func

    def match2vars(self, func):
        assert not self._match2vars, 'match2vars already set'
        self._match2vars = func
        return func

    def vars2url(self, func):
        assert not self._vars2url, 'vars2url already set'
        self._vars2url = func
        return func

    def vars2urlparts(self, func):
        assert not self._vars2urlparts, 'vars2urlpart already set'
        self._vars2urlparts = func
        return func


class RouterConfiguration:

    def __init__(self):
        self.routes = {}

    def route(self, name, urltpl, *, before=[], after=[], tpl=None):
        if isinstance(before, str) or not hasattr(before, '__iter__'):
            before = (before,)
        if isinstance(after, str) or not hasattr(after, '__iter__'):
            after = (after,)
        if not isinstance(urltpl, UrlTemplate):
            urltpl = PatternUrlTemplate(urltpl)

        def capture_route(func):
            if name in self.routes:
                raise DuplicateRouteDefinition(name)
            route = RouteConfiguration(name, urltpl, tpl, func)
            for other in before:
                if isinstance(other, RouteConfiguration):
                    other = other.name
                route.before.append(other)
            for other in after:
                if isinstance(other, RouteConfiguration):
                    other = other.name
                route.after.append(other)
            self.routes[name] = route
            return route
        return capture_route

    def define_static_route(self, name, urltpl, rootdir, *,
                            force_mimetype=None, **kwargs):
        mimetype = (None, None)
        if isinstance(force_mimetype, str):
            mimetype = (force_mimetype, None)
        elif force_mimetype:
            mimetype = force_mimetype

        @self.route(name, urltpl, **kwargs)
        def static_route(ctx, path):
            base = rootdir
            if callable(rootdir):
                base = rootdir(ctx, path)
            path = os.path.join(base, path)
            if not os.path.commonprefix((base, path)).startswith(base):
                # the path points outside of base
                raise HTTPNotFound()
            try:
                ctx.http.response.app_iter = open(path, 'rb')
            except (FileNotFoundError, IsADirectoryError):
                raise HTTPNotFound()
            content_type, content_encoding = mimetype
            if not content_type:
                guess = mimetypes.guess_type(path, strict=False)
                if guess[0]:
                    content_type, content_encoding = guess
            ctx.http.response.content_type = content_type
            if content_encoding:
                ctx.http.response.content_encoding = content_encoding

    def sorted_routes(self):
        try:
            depsolv = DependencySolver()
            constrained = set(r for r in self.routes.values()
                              if r.before or r.after)
            unconstrained = set(self.routes.values()) - constrained
            for r1, r2 in permutations(unconstrained, 2):
                if r1.urltpl.equals(r2.urltpl):
                    continue
                if r1.urltpl < r2.urltpl:
                    depsolv.add_dependency(r1.name, r2.name)
                else:
                    depsolv.add_dependency(r2.name, r1.name)
            for route in constrained:
                self._insert_constrained(depsolv, route)
            for route in unconstrained:
                # quite improbable case, but this scenario does exist (all
                # routes unconstrained and equal, for example)
                depsolv.add_dependency(route.name)
            return list(self.routes[n]
                        for n in reversed(depsolv.solve()))
        except ScoreInitDependencyLoop as e:
            raise DependencyLoop(e.loop)

    def _insert_constrained(self, depsolv, route):
        for before in route.before:
            self._insert_before(depsolv, route, before)
        for after in route.after:
            self._insert_after(depsolv, route, after)

    def _insert_before(self, depsolv, route, other):
        route_predecessors = depsolv.direct_dependencies(route.name)
        if other in route_predecessors:
            depsolv.add_dependency(route.name, other)
            depsolv.solve()  # raises ScoreInitDependencyLoop
        other_predecessors = depsolv.direct_dependencies(other)
        for other_predecessor in other_predecessors:
            if route.urltpl < self.routes[other_predecessor].urltpl:
                try:
                    self._insert_before(depsolv, route, other_predecessor)
                    break
                except ScoreInitDependencyLoop:
                    pass
        else:
            depsolv.add_dependency(route.name, other)
            for other_predecessor in depsolv.direct_dependencies(other):
                if self.routes[other_predecessor].urltpl < route.urltpl:
                    if depsolv.has_direct_dependency(other_predecessor, other):
                        depsolv.remove_dependency(other_predecessor, other)
                        depsolv.add_dependency(other_predecessor, route.name)

    def _insert_after(self, depsolv, route, other):
        route_successors = depsolv.direct_dependents(route.name)
        if other in route_successors:
            depsolv.add_dependency(other, route.name)
            depsolv.solve()  # raises ScoreInitDependencyLoop
        other_successors = depsolv.direct_dependents(other)
        for other_successor in other_successors:
            if self.routes[other_successor].urltpl < route.urltpl:
                try:
                    self._insert_after(depsolv, route, other_successor)
                    break
                except ScoreInitDependencyLoop:
                    pass
        else:
            depsolv.add_dependency(other, route.name)
            for other_successor in depsolv.direct_dependents(other):
                if route.urltpl < self.routes[other_successor].urltpl:
                    if depsolv.has_direct_dependency(other, other_successor):
                        depsolv.remove_dependency(other, other_successor)
                        depsolv.add_dependency(route.name, other_successor)
