.. _http_glossary:

.. glossary::

    request router
        The request router (also referred to as the *http router*) is the part
        of an HTTP application that decides which :term:`route` is responsible
        for handling a particular HTP request.

    route
        A function designed to handle a specific URL. The URL may contain
        variables, as described in the :ref:`narrative documentation of the
        router <http_router>`.

    preroute
        A function that will be called before the actual :term:`route` to a
        request is invoked. Note that the preroute will *only* be invoked, if
        there actually is a route. It will not be invoked for requests, where
        none of the configured routes mathed (i.e. 404 responses).
