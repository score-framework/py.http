# Copyright © 2015,2016 STRG.AT GmbH, Vienna, Austria
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
import networkx as nx
from score.init import InitializationError as ScoreInitializationError
from itertools import permutations
import functools


class InitializationError(ScoreInitializationError):

    def __init__(self, msg):
        import score.http
        super().__init__(score.http, msg)


class DependencyLoop(InitializationError):

    def __init__(self, loop):
        super().__init__('Cannot resolve ordering of the following routes:\n' +
                         '\n'.join(map(lambda x: ' - ' + x[0], loop)))


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

    def clone(self):
        new = self.__class__()
        new.routes.update(self.routes)
        return new

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

    # TODO: add support for static routes

    def sorted_routes(self):
        graph = nx.DiGraph()
        constrained = set(r for r in self.routes.values()
                          if r.before or r.after)
        unconstrained = set(self.routes.values()) - constrained
        for r1, r2 in permutations(unconstrained, 2):
            if r1.urltpl.equals(r2.urltpl):
                continue
            if r1.urltpl < r2.urltpl:
                graph.add_edge(r1.name, r2.name)
            else:
                graph.add_edge(r2.name, r1.name)
        for route in constrained:
            self._insert_constrained(graph, route)
        for route in unconstrained:
            if not graph.has_node(route.name):
                # quite improbable case, but this scenario does exist (all
                # routes unconstrained and equal, for example)
                graph.add_edge(None, route.name)
        try:
            loop = nx.find_cycle(graph)
            raise DependencyLoop(loop)
        except nx.NetworkXNoCycle:
            pass
        return list(self.routes[n]
                    for n in nx.topological_sort(graph)
                    if n is not None)

    def _insert_constrained(self, graph, route):
        for before in route.before:
            self._insert_before(graph, route, before)
        for after in route.after:
            self._insert_after(graph, route, after)

    def _insert_before(self, graph, route, other):
        try:
            route_predecessors = graph.predecessors(route.name)
        except nx.NetworkXError:
            route_predecessors = []
        if other in route_predecessors:
            graph.add_edge(route.name, other)
            raise DependencyLoop(nx.find_cycle(graph, route.name))
        try:
            other_predecessors = graph.successors(other)[:]
        except nx.NetworkXError:
            other_predecessors = []
        for other_predecessor in other_predecessors:
            if route.urltpl < self.routes[other_predecessor].urltpl:
                try:
                    self._insert_before(graph, route, other_predecessor)
                    break
                except DependencyLoop:
                    pass
        else:
            graph.add_edge(route.name, other)
            for other_predecessor in graph.predecessors(other)[:]:
                if self.routes[other_predecessor].urltpl < route.urltpl:
                    try:
                        graph.remove_edge(other_predecessor, other)
                    except nx.NetworkXError:
                        pass
                    else:
                        graph.add_edge(other_predecessor, route.name)

    def _insert_after(self, graph, route, other):
        try:
            route_successors = graph.successors(route.name)
        except nx.NetworkXError:
            route_successors = []
        if other in route_successors:
            graph.add_edge(other, route.name)
            raise DependencyLoop(nx.find_cycle(graph, route.name))
        try:
            other_successors = graph.successors(other)[:]
        except nx.NetworkXError:
            other_successors = []
        for other_successor in other_successors:
            if self.routes[other_successor].urltpl < route.urltpl:
                try:
                    self._insert_after(graph, route, other_successor)
                    break
                except DependencyLoop:
                    pass
        else:
            graph.add_edge(other, route.name)
            for other_successor in graph.successors(other)[:]:
                if route.urltpl < self.routes[other_successor].urltpl:
                    try:
                        graph.remove_edge(other, other_successor)
                    except nx.NetworkXError:
                        pass
                    else:
                        graph.add_edge(route.name, other_successor)
