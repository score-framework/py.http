from score.router import PatternUrl


def test_empty_pattern():
    url = PatternUrl('')
    assert url


def test_string_pattern():
    url = PatternUrl('foo')
    assert url.pattern == '/foo'


def test_equal_comparison():
    url1 = PatternUrl('a')
    url2 = PatternUrl('a')
    assert url1.equals(url2)
    url1 = PatternUrl('{a}')
    url2 = PatternUrl('{a}')
    assert url1.equals(url2)


def test_string_comparison():
    url1 = PatternUrl('a')
    url2 = PatternUrl('b')
    assert url1 != url2
    assert url1 < url2
    assert url1 <= url2
    assert not (url1 > url2)


def test_string_vs_pattern_1():
    url1 = PatternUrl('a')
    url2 = PatternUrl('{b}')
    assert url1 < url2
    assert url1 <= url2
    assert not (url1 > url2)


def test_string_vs_pattern_2():
    url1 = PatternUrl('b')
    url2 = PatternUrl('{a}')
    assert url1 < url2
    assert url1 <= url2
    assert not (url1 > url2)


def test_equal_patterns_1():
    url1 = PatternUrl('{a}')
    url2 = PatternUrl('{b}')
    assert url1.equals(url2)


def test_equal_patterns_2():
    url1 = PatternUrl('a{a}')
    url2 = PatternUrl('a{b}')
    assert url1.equals(url2)


def test_equal_patterns_3():
    url1 = PatternUrl('{a}a')
    url2 = PatternUrl('{b}a')
    assert url1.equals(url2)


def test_equal_patterns_4():
    url1 = PatternUrl('{a}/a')
    url2 = PatternUrl('{b}/a')
    assert url1.equals(url2)


def test_string_precedence_1():
    url1 = PatternUrl('a/{a}/a')
    url2 = PatternUrl('a/{b}')
    assert url1 < url2


def test_string_precedence_2():
    url1 = PatternUrl('a/{a}')
    url2 = PatternUrl('b/{b}')
    assert url1 < url2


def test_string_precedence_3():
    url1 = PatternUrl('{a}/a')
    url2 = PatternUrl('{b}/b')
    assert url1 < url2


def test_url_generation_1():
    url = PatternUrl('/{foo}')
    assert url.generate(foo='bar') == '/bar'


def test_url_generation_2():
    url = PatternUrl(r'/{foo>\d+}')
    assert url.generate(foo=123) == '/123'


'/{article.author.slug}/{article.slug}-{article.id}'
