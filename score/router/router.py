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

from .url import PatternUrl
import networkx as nx
from score.init import InitializationError as ScoreInitializationError
from webob import Response
from itertools import permutations


class InitializationError(ScoreInitializationError):
    pass


class DependencyLoop(InitializationError):
    pass


class DuplicateRouteDefinition(InitializationError):
    pass


class Route:

    def __init__(self, name, url, tpl, func):
        self.name = name
        self.url = url
        self.tpl = tpl
        self.func = func
        self._preconditions = []
        self._match2vars = None
        self._vars2url = None
        self._vars2urlpart = None
        self.before = []
        self.after = []

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def handle(self, ctx, request):
        match = self.url.regex.match(request.path)
        if not match:
            return None
        variables = {}
        for part in self.parts:
            if not part.variable:
                continue
            variables[part.variable] = match.group(part.variable)
        if self._match2vars:
            variables = self.match2vars(variables)
        for callback in self._preconditions:
            if not callback(ctx, request, variables):
                return None
        result = self.func(ctx, **variables)
        if isinstance(result, Response):
            return result
        # TODO: incomplete

    def precondition(self, func):
        self._preconditions.append(func)
        return func

    def match2vars(self, func):
        assert not self._match2vars, 'match2vars already set'
        self._match2vars = func
        return func

    def vars2url(self, func):
        assert not self._vars2url, 'vars2url already set'
        self._vars2url = func
        return func

    def vars2urlpart(self, func):
        assert not self._vars2urlpart, 'vars2urlpart already set'
        self._vars2urlpart = func
        return func


class Router:

    def __init__(self):
        self.finalized = False
        self.routes = {}

    def handle(self, request):
        assert self.finalized, 'Router not finalized'
        for route in self.sorted_routes:
            response = route.handle(request)
            if response is None:
                continue
            # TODO: incomplete
            return response

    def route(self, name, url, *, before=[], after=[], tpl=None):
        if isinstance(before, str) or not hasattr(before, '__iter__'):
            before = (before,)
        if isinstance(after, str) or not hasattr(after, '__iter__'):
            after = (after,)

        def capture_route(func):
            assert not self.finalized, 'Router already finalized'
            if name in self.routes:
                raise DuplicateRouteDefinition(name)
            route = Route(name, PatternUrl(url), tpl, func)
            for other in before:
                if isinstance(other, Route):
                    other = other.name
                route.before.append(other)
            for other in after:
                if isinstance(other, Route):
                    other = other.name
                route.after.append(other)
            self.routes[name] = route
            return route
        return capture_route

    def finalize(self):
        self.finalized = True
        graph = nx.DiGraph()
        constrained = set(r for r in self.routes.values()
                          if r.before or r.after)
        unconstrained = set(self.routes.values()) - constrained
        for r1, r2 in permutations(unconstrained, 2):
            if r1.url.equals(r2.url):
                continue
            if r1.url < r2.url:
                graph.add_edge(r1.name, r2.name)
            else:
                graph.add_edge(r2.name, r1.name)
        for route in constrained:
            self._insert_constrained(graph, route)
        for route in unconstrained:
            if not graph.has_node(route.name):
                # quite improbable case, but this scenario *does* exist (all
                # routes unconstrained and equal, for example)
                graph.add_edge(None, route.name)
        for loop in nx.simple_cycles(graph):
            raise DependencyLoop(loop)
        self.sorted_routes = list(self.routes[n]
                                  for n in nx.topological_sort(graph)
                                  if n is not None)

    def _insert_constrained(self, graph, route):
        for before in route.before:
            if before not in self.routes:
                raise InitializationError(
                    'Given before-dependency not found: (*%s* -> %s)' %
                    (before, route))
            loop = self._insert_before(graph, route, before)
            if loop:
                raise DependencyLoop(loop)
        for after in route.after:
            if after not in self.routes:
                raise InitializationError(
                    'Given after-dependency not found: (%s -> *%s*)' %
                    (route, after))
            loop = self._insert_after(graph, route, after)
            if loop:
                raise DependencyLoop(loop)

    def _insert_before(self, graph, route, other):
        graph.add_edge(route.name, other)
        for loop in nx.simple_cycles(graph):
            graph.remove_edge(route.name, other)
            return loop
        for predecessor in graph.predecessors_iter(other):
            preroute = self.routes[predecessor]
            if route.url < preroute.url:
                self._insert_before(graph, route, predecessor)
            elif route.url > preroute.url:
                graph.add_edge(predecessor, route.name)
                if any(nx.simple_cycles(graph)):
                    graph.remove_edge(predecessor, route.name)
        return None

    def _insert_after(self, graph, route, other):
        graph.add_edge(other, route.name)
        for loop in nx.simple_cycles(graph):
            graph.remove_edge(other, route.name)
            return loop
        for successor in graph.successors_iter(other):
            postroute = self.routes[successor]
            if route.url > postroute.url:
                self._insert_after(graph, route, successor)
            elif route.url < postroute.url:
                graph.add_edge(route.name, successor)
                if any(nx.simple_cycles(graph)):
                    graph.remove_edge(route.name, successor)
        return None


# router = Router()
# route = router.route
#
#
# @route('article', '/{article.author.slug}/{article.slug}-{article.id}')
# def article(ctx, article):
#     pass
#
#
# @article.precondition
# def article_precondition(ctx, article):
#     return article.is_online
#
#
# @article.POST
# def article_post(ctx, article):
#     return ctx.route('article')(article)
#
#
# @article.match2vars
# def article_match2vars(ctx, match):
#     return ctx.db.query('Article').get(int(match['article.id']))
#
#
# @article.vars2url
# def article_vars2url(ctx, article):
#     return '/%s/%s/%d' % (
#         article.author.username,
#         article.slug,
#         article.id,
#     )
#
#
# @article.vars2urlparts
# def article_vars2urlparts(ctx, article):
#     return {
#         'article.author.slug': article.author.username,
#     }
#
#
# article.url(some_article)
