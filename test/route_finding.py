from score.ctx import init as init_score_ctx
from score.http import init, RouterConfiguration as Router


def init_ctx():
    ctx = init_score_ctx()
    ctx._finalize(object())
    return ctx


def test_find_url_route_0():
    router = Router()
    router.route('route', '/foo')(
        lambda: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    assert conf.find_route_for('/foo').name == 'route'


def test_find_url_route_1():
    router = Router()
    router.route('route', '/foo/{bar}')(
        lambda var: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    assert conf.find_route_for('/foo/bar').name == 'route'
    assert conf.find_route_for('/foo/baz').name == 'route'
    assert conf.find_route_for('/foo/qaz').name == 'route'


def test_find_url_route_2():
    router = Router()
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    assert conf.find_route_for('/foo') == None


def test_find_url_route_3():
    router = Router()
    router.route('route', '/foo')(
        lambda var: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    assert conf.find_route_for('/foo').name == 'route'
    assert conf.find_route_for('/bar') == None
