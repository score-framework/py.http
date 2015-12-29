from score.http import RouterConfiguration as Router


def test_empty_url():
    router = Router()
    callcount = 0

    @router.route('route', '')
    def route():
        nonlocal callcount
        callcount += 1
    assert callcount == 0
    route()
    assert callcount == 1


def test_args():
    router = Router()
    callcount = 0

    @router.route('route', '')
    def route(*args):
        assert args == (1, 2)
        nonlocal callcount
        callcount += 1
    assert callcount == 0
    route(1, 2)
    assert callcount == 1


def test_kwargs():
    router = Router()
    callcount = 0

    @router.route('route', '')
    def route(one=None, two=None):
        assert one == 1
        assert two == 2
        nonlocal callcount
        callcount += 1
    assert callcount == 0
    route(one=1, two=2)
    assert callcount == 1
