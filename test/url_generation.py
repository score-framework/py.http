from score.ctx import init as init_ctx
from score.http import init, RouterConfiguration as Router
from score.http._urltpl import InvalidVariable, MissingVariable
import pytest
from unittest.mock import Mock


def test_empty_route():
    router = Router()
    router.route('route', '')(
        lambda: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    assert conf.route('route').url(conf.ctx.Context()) == '/'


def test_string_route():
    router = Router()
    router.route('route', 'home')(
        lambda: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    assert conf.route('route').url(conf.ctx.Context()) == '/home'


def test_variable_1():
    router = Router()
    router.route('route', '/{var}')(
        lambda var: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    assert conf.route('route').url(conf.ctx.Context(), 'foo') == '/foo'


def test_variable_2():
    router = Router()
    router.route('route', '/foo/{var>\d+}')(
        lambda var: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    assert conf.route('route').url(conf.ctx.Context(), 123) == '/foo/123'


def test_variable_3():
    router = Router()
    router.route('route', '/foo/{var>\d+}')(
        lambda var: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    with pytest.raises(InvalidVariable):
        conf.route('route').url(conf.ctx.Context(), 'bar')


def test_pathed_variable_1():
    router = Router()
    router.route('route', '/{article.id}')(
        lambda article: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    assert conf.route('route').url(conf.ctx.Context(), Mock(id=123)) == '/123'


def test_pathed_variable_2():
    router = Router()
    router.route('route', '/{article.author.slug}/{article.id}')(
        lambda article: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    article = Mock(id=123, author=Mock(slug='author-slug'))
    assert conf.route('route').url(conf.ctx.Context(), article) == '/author-slug/123'


def test_pathed_variable_3():
    router = Router()
    router.route('route', '/{article.author.slug}/{article.id}')(
        lambda article: None)
    conf = init({'router': router}, ctx=init_ctx())
    conf._finalize()
    with pytest.raises(MissingVariable):
        conf.route('route').url(conf.ctx.Context(), object())
