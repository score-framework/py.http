from score.ctx import init as init_ctx
from score.http import (
    init, RouterConfiguration as Router, DependencyLoop,
    DuplicateRouteDefinition)
from score.http._conf import RouteConfiguration
import pytest
from unittest.mock import Mock


def test_empty_router():
    router = Router()
    init({'router': router}, ctx=init_ctx())._finalize()


def test_adding_routes():
    router = Router()

    @router.route('foo', '/foo')
    def foo():
        pass
    assert isinstance(foo, RouteConfiguration)


def test_simple_route_comparison_1():
    router = Router()
    router.route('a', '/a')(Mock())
    router.route('b', '/b')(Mock())
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    sorted_routes = list(conf.routes.keys())
    assert 'a' in sorted_routes
    assert 'b' in sorted_routes
    assert sorted_routes.index('a') < sorted_routes.index('b')


def test_simple_route_comparison_2():
    """
    same as test_simple_route_comparison_1, but with definition order reversed.
    """
    router = Router()
    router.route('b', '/b')(Mock())
    router.route('a', '/a')(Mock())
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    sorted_routes = list(conf.routes.keys())
    assert 'a' in sorted_routes
    assert 'b' in sorted_routes
    assert sorted_routes.index('a') < sorted_routes.index('b')


def test_redefinition():
    router = Router()
    router.route('a', '/a')(Mock())
    with pytest.raises(DuplicateRouteDefinition):
        router.route('a', '/a')(Mock())


def test_custom_order_1():
    router = Router()
    b = router.route('b', '/b')(Mock())
    router.route('a', '/a', after=b)(Mock())
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    sorted_routes = list(conf.routes.keys())
    assert 'a' in sorted_routes
    assert 'b' in sorted_routes
    assert sorted_routes.index('b') < sorted_routes.index('a')


def test_custom_order_2():
    """
    same as test_custom_order_1, but passing a.after as string
    """
    router = Router()
    router.route('b', '/b')(Mock())
    router.route('a', '/a', after='b')(Mock())
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    sorted_routes = list(conf.routes.keys())
    assert 'a' in sorted_routes
    assert 'b' in sorted_routes
    assert sorted_routes.index('b') < sorted_routes.index('a')


def test_custom_order_3():
    router = Router()
    router.route('a', '/a')(Mock())
    router.route('b', '/b')(Mock())
    router.route('c', '/c', before='b')(Mock())
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    sorted_routes = list(conf.routes.keys())
    assert 'a' in sorted_routes
    assert 'b' in sorted_routes
    assert 'c' in sorted_routes
    assert sorted_routes.index('a') < sorted_routes.index('c')
    assert sorted_routes.index('c') < sorted_routes.index('b')


def test_custom_order_4():
    router = Router()
    router.route('a', '/a')(Mock())
    router.route('b', '/b')(Mock())
    router.route('c', '/c', before='a')(Mock())
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    sorted_routes = list(conf.routes.keys())
    assert sorted_routes == ['c', 'a', 'b']


def test_custom_order_5():
    router = Router()
    router.route('a', '/a')(Mock())
    router.route('b', '/b', before='a')(Mock())
    router.route('c', '/c', before='a')(Mock())
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    sorted_routes = list(conf.routes.keys())
    assert 'a' in sorted_routes
    assert 'b' in sorted_routes
    assert 'c' in sorted_routes
    assert sorted_routes.index('b') < sorted_routes.index('a')
    assert sorted_routes.index('c') < sorted_routes.index('a')


def test_loop_1():
    router = Router()
    router.route('a', '/a', before='a')(Mock())
    with pytest.raises(DependencyLoop):
        init({'router': router}, ctx=init_ctx())._finalize()


def test_loop_2():
    router = Router()
    router.route('a', '/a', before='b')(Mock())
    router.route('b', '/b', before='a')(Mock())
    with pytest.raises(DependencyLoop):
        init({'router': router}, ctx=init_ctx())._finalize()


def test_loop_3():
    router = Router()
    router.route('a', '/a', before='b')(Mock())
    router.route('b', '/b', before='c')(Mock())
    router.route('c', '/c', before='a')(Mock())
    with pytest.raises(DependencyLoop):
        init({'router': router}, ctx=init_ctx())._finalize()
