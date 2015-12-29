from score.http import RouterConfiguration as Router
from unittest.mock import Mock


def test_empty_url():
    router = Router()
    mock = Mock()
    route = router.route('route', '')(mock)
    route()
    mock.assert_called_once_with()
