from score.router import Router, DependencyLoop, DuplicateRouteDefinition
from score.router.router import Route
import pytest


def test_finalize_empty_router():
    router = Router()
    router.finalize()


def test_adding_routes():
    router = Router()
    @router.route('foo', '/foo')
    def foo():
        pass
    assert isinstance(foo, Route)


def test_simple_route_comparison_1():
    router = Router()
    @router.route('a', '/a')
    def a():
        pass
    @router.route('b', '/b')
    def b():
        pass
    router.finalize()
    assert a in router.sorted_routes
    assert b in router.sorted_routes
    assert router.sorted_routes.index(a) < router.sorted_routes.index(b)


def test_simple_route_comparison_2():
    """
    same as test_simple_route_comparison_1, but with definition order reversed.
    """
    router = Router()
    @router.route('b', '/b')
    def b():
        pass
    @router.route('a', '/a')
    def a():
        pass
    router.finalize()
    assert a in router.sorted_routes
    assert b in router.sorted_routes
    assert router.sorted_routes.index(a) < router.sorted_routes.index(b)


def test_redefinition():
    router = Router()
    @router.route('b', '/b')
    def b():
        pass
    with pytest.raises(DuplicateRouteDefinition):
        @router.route('b', '/b')
        def b():
            pass


def test_custom_order_1():
    router = Router()
    @router.route('b', '/b')
    def b():
        pass
    @router.route('a', '/a', after=b)
    def a():
        pass
    router.finalize()
    assert a in router.sorted_routes
    assert b in router.sorted_routes
    assert router.sorted_routes.index(b) < router.sorted_routes.index(a)


def test_custom_order_2():
    router = Router()
    @router.route('b', '/b')
    def b():
        pass
    @router.route('a', '/a', after='b')
    def a():
        pass
    router.finalize()
    assert a in router.sorted_routes
    assert b in router.sorted_routes
    assert router.sorted_routes.index(b) < router.sorted_routes.index(a)


def test_custom_order_3():
    router = Router()
    @router.route('a', '/a')
    def a():
        pass
    @router.route('b', '/b')
    def b():
        pass
    @router.route('c', '/c', before=b)
    def c():
        pass
    router.finalize()
    assert a in router.sorted_routes
    assert b in router.sorted_routes
    assert c in router.sorted_routes
    assert router.sorted_routes.index(a) < router.sorted_routes.index(c)
    assert router.sorted_routes.index(c) < router.sorted_routes.index(b)


def test_custom_order_4():
    router = Router()
    @router.route('a', '/a')
    def a():
        pass
    @router.route('b', '/b')
    def b():
        pass
    @router.route('c', '/c', before=a)
    def c():
        pass
    router.finalize()
    assert a in router.sorted_routes
    assert b in router.sorted_routes
    assert c in router.sorted_routes
    assert router.sorted_routes.index(c) < router.sorted_routes.index(a)
    assert router.sorted_routes.index(a) < router.sorted_routes.index(b)


def test_custom_order_5():
    router = Router()
    @router.route('a', '/a')
    def a():
        pass
    @router.route('b', '/b', before=a)
    def b():
        pass
    @router.route('c', '/c', before=a)
    def c():
        pass
    router.finalize()
    assert a in router.sorted_routes
    assert b in router.sorted_routes
    assert c in router.sorted_routes
    assert router.sorted_routes.index(b) < router.sorted_routes.index(c)
    assert router.sorted_routes.index(c) < router.sorted_routes.index(a)


def test_loop_1():
    router = Router()
    @router.route('b', '/b', before='b')
    def b():
        pass
    with pytest.raises(DependencyLoop):
        router.finalize()


def test_loop_2():
    router = Router()
    @router.route('a', '/a', before='b')
    def a():
        pass
    @router.route('b', '/b', before='a')
    def b():
        pass
    with pytest.raises(DependencyLoop):
        router.finalize()


def test_loop_3():
    router = Router()
    @router.route('a', '/a', before='b')
    def a():
        pass
    @router.route('b', '/b', before='c')
    def b():
        pass
    @router.route('c', '/c', before='a')
    def c():
        pass
    with pytest.raises(DependencyLoop):
        router.finalize()
