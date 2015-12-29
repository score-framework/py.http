from score.ctx import init as init_ctx
from score.http import init, RouterConfiguration as Router
from score.http.url import InvalidVariable
import pytest
from unittest.mock import Mock


def test_empty_route():
    router = Router()
    router.route('route', '')(
        lambda: None)
    conf = init({'router': router}, ctx=init_ctx())
    assert conf.route('route').url() == '/'


def test_string_route():
    router = Router()
    router.route('route', 'home')(
        lambda: None)
    conf = init({'router': router}, ctx=init_ctx())
    assert conf.route('route').url() == '/home'


def test_variable_1():
    router = Router()
    router.route('route', '/{var}')(
        lambda var: None)
    conf = init({'router': router}, ctx=init_ctx())
    assert conf.route('route').url('foo') == '/foo'


def test_variable_2():
    router = Router()
    router.route('route', '/foo/{var>\d+}')(
        lambda var: None)
    conf = init({'router': router}, ctx=init_ctx())
    assert conf.route('route').url(123) == '/foo/123'


def test_variable_3():
    router = Router()
    router.route('route', '/foo/{var>\d+}')(
        lambda var: None)
    conf = init({'router': router}, ctx=init_ctx())
    with pytest.raises(InvalidVariable):
        conf.route('route').url('bar')


def test_pathed_variable_1():
    router = Router()
    router.route('route', '/{article.id}')(
        lambda article: None)
    conf = init({'router': router}, ctx=init_ctx())
    assert conf.route('route').url(Mock(id=123)) == '/123'


def test_pathed_variable_2():
    router = Router()
    router.route('route', '/{article.author.slug}/{article.id}')(
        lambda article: None)
    conf = init({'router': router}, ctx=init_ctx())
    article = Mock(id=123, author=Mock(slug='author-slug'))
    assert conf.route('route').url(article) == '/author-slug/123'


def test_pathed_variable_3():
    router = Router()
    router.route('route', '/{article.author.slug}/{article.id}')(
        lambda article: None)
    conf = init({'router': router}, ctx=init_ctx())
    with pytest.raises(InvalidVariable):
        conf.route('route').url(object())
