.. module:: score.http
.. role:: confkey
.. role:: confdefault

**********
score.http
**********

This module consists of the only essential feature required to write an HTTP
application: The :term:`request router`. It also provides appropriate functions
to wrap the router to form a valid WSGI_ application.

.. _WSGI: https://en.wikipedia.org/wiki/Web_Server_Gateway_Interface

Quickstart
==========

Create a :term:`router <request router>`, which will be responsible for
efficiently deciding which function should be called given an arbitrary HTTP
request:

.. code-block:: python

    from score.http import RouterConfiguration

    routeconf = RouterConfiguration()

Define some :term:`routes <route>` with your new router:

.. code-block:: python

    @routeconf.route('hello', '/')
    def hello(ctx):
        return 'Hello world!'

    @routeconf.route('hello/name', '/{name}')
    def hello_name(ctx, name):
        return 'Hello, %s!' % name

If this code is in the package *greeter*, for example, the configuration
of the module should look like the following to make use of these routes:

.. code-block:: ini

    [http]
    router = greeter.routeconf

You can now create URLs to these routes directly from within your
:term:`context <context object>`:

>>> ctx.score.http.url(ctx, 'hello/name', 'Sir Lancelot')
/Sir%20Lancelot

When you open the URL in your browser, the router will make sure that your
``hello_name`` function is called to generate a response to the incoming
request.


Configuration
=============

.. autofunction:: score.http.init


Details
=======

.. _http_router:

Router Compilation
------------------

During the module initialization, the routes captured by the helper object will
be analyzed, sorted and compiled into an efficient router. Every route will
provide a regular expression that the request URL must match. Note that this
really is not sufficient to decide if a route matches, merely the first
condition that must be met.

The above routes will generate to the following two regular expressions::

    ^/$
    ^/[^/]*$

.. note::

    Regular expressions are incredibly hard to read. That's why we decided to
    give really *minimal* examples, because the actual expressions require a
    lot of attention (apart from quite some knowledge) to understand. The regex
    of the very simple *hello/name* route would actually look like this::

        ^/(?P<name>[^/]*)$

Variables in route names will be translated to the regular expression `[^/]*`
by default, i.e. any number of non-slash characters. It is possible to change
this regular expression by declaring it after a ``>`` character in the
variable name within the URL template:

.. code-block:: python

    @routeconf.route('hello/name', '/{name>[a-zA-Z]*}')
    def hello_name(ctx, name):
        return 'Hello, %s!' % name

The regular expressions will then be sorted to determine the order in which
they should be tested. This is very important: if the above functions were
defined in reverse order, the *hello* route would never match, since the router
would assume that the *hello/name* route was requested with an empty string as
*name*.


.. _http_route_sorting:

Route Sorting
^^^^^^^^^^^^^

So how do we define the order of the routes? This is actually feature of the
:class:`UrlTemplates <.UrlTemplate>` class: It implements the
less-than-operator and a function :meth:`equals <.UrlTemplate.equals>` to use
for sorting the routes.

If you define the URL templates as strings (as encouraged throughout the
documentation), the routes will internally create a
:class:`PatternUrlTemplate`. Your routes will then be sorted using a set of
rules taking the amount and positions of variables into account.

There are some circumstances, where it is not possible to determine the order
automatically. Mainly because the compiler does not analyze regular
expressions. This means that it will not dare guess in which order the
following routes should be tested:

.. code-block:: python

    @routeconf.route('hello/user', '/{user>\d+}')
    def hello_user(ctx, user):
        # ...

    @routeconf.route('hello/name', '/{name>[a-zA-Z]*}')
    def hello_name(ctx, name):
        # ...

All the module sees are two separate routes consisting of a regular expression
and it will raise an Exception during initialization. You will have to define
ordering of these rules manually in such scenarios. You can either pass a
*before* argument, or an *after* argument to either route:

.. code-block:: python

    @routeconf.route('hello/user', '/{user>\d+}', before='hello/name')
    def hello_user(ctx, user):
        # ...

    @routeconf.route('hello/name', '/{name>[a-zA-Z ]*}')
    def hello_name(ctx, name):
        # ...


Creating URLs
-------------

Once the module is configured, it can generate URLs to any route through
its :meth:`score.http.ConfiguredHttpModule.url` function. This function can, of
course, be accessed through the usual :class:`score.init.ConfiguredScore`
object in any given :term:`context <context object>`:

>>> ctx.score.http.url(ctx, 'hello/name', 'Sir Lancelot')
/Sir%20Lancelot

But since this is quite a common operation in web applications, the module also
registers a shortcut function as :term:`context member`:

>>> ctx.url('hello/name', 'Sir Lancelot')
/Sir%20Lancelot

The :meth:`url <score.http.ConfiguredHttpModule.url>` method expects the same
arguments as the underlying function, just as one would actually call the
function. The :class:`.UrlTemplate` of the route is then instructed to generate
the URL out of the given variables.

During this process, the module will also convert dotted variable names in the
:class:`.UrlTemplate` to the correct values by accessing the object's
attributes as specified:

.. code-block:: python

    @router.route('profile', '/user/{user.username}')
    def profile(ctx, user):
        return 'Hello, %s!' % user.username

>>> knight = ctx.db.query(db.User).first()
>>> knight.username
sirlancelot
>>> ctx.url('profile', knight)
/user/sirlancelot

It is further possible to add a query string and/or an anchor specification by
passing the keyword arguments *_query* and *_anchor*:

>>> ctx.url('profile', knight, _query={'sillymode': 'true'}, _anchor='friends')
/user/sirlancelot?sillymode=true#friends


.. _http_url_conversion:

URL conversions
---------------

We have already seen that the default UrlTemplate classes can handle variables
in URLs. The design philosophy here is that routes should not have to behave
differently just because they are a route. This means that routes should not
have to decode URLs or transform variables assuming they were extracted from
the URL. In other words: the function itself should be oblivious to the fact
that it is a route in almost all cases.

The last code sample correctly demonstrated this: it is expecting a user object
(not a username). In order to achieve this separation of concerns, we must
teach the route two things:

- how to convert a *user* object to the *user.username* variable (if we are not
  happy with the default behaviour of accessing the *user* object's *username*
  member) and

- how to determine obtain a *user* object, when all we have is a URL.

Variables to URL
^^^^^^^^^^^^^^^^

In most scenarios, the first issue can be handed off to the router, as the
default behaviour should be sufficient. But it is possible to override this
behaviour by providing a ``vars2urlparts`` function to the route:

.. code-block:: python

    @router.route('profile', '/user/{user.username}')
    def profile(ctx, user):
        return 'Hello, %s!' % user.username

    @profile.vars2urlparts
    def profile_vars2urlparts(ctx, user):
        return {
            'user.username': user.username.lower()
        }

As you can see, the ``vars2urlparts`` function opf a route must accept the
exact same parameters as the route itself. It must then return a `dict` mapping
*all* variables in the url template to their values.

If this is not sufficient, it is also possible to provide a more generic, but
also a much harder-to-implement function call ``vars2url``. This one would then
be responsible to generate the complete url including any query string, and
anchor:

.. code-block:: python

    import urllib.parse

    @router.route('profile', '/user/{user.username}')
    def profile(ctx, user):
        return 'Hello, %s!' % user.username

    @profile.vars2url
    def profile_vars2url(ctx, user, _query=None, _anchor=None):
        url = '/user/'
        url += urllib.parse.quote(user.username.lower(), safe='')
        if _query:
            url += '?' + urllib.parse.urlencode(_query)
        if _anchor:
            url += '#' + urllib.parse.quote(_anchor, safe='')
        return url


URL to Variables
^^^^^^^^^^^^^^^^

The inverse operation—converting regular expression matches to python
variables—can be done using another function called ``match2vars``:

.. code-block:: python

    @router.route('profile', '/user/{user.username}')
    def profile(ctx, user):
        return 'Hello, %s!' % user.username

    @profile.match2vars
    def profile_match2vars(ctx, matches):
        user = ctx.db.query(User).\
            filter(User.username == matches['user.username'])).\
            first()
        if user:
            return {
                'user': user
            }

As you can see, the implementation of such a function is quite simple: It
receives a `dict` containing relevant parts of the regular expression match and
is expected to return a new `dict` containing the arguments to the route. If
the variables in the match `dict` are not valid to enter the route, it must
instead return `None`.

There is some good news, though, if you're also using `score.db`: the router
will be able to lookup your objects automatically in most cases, as long as you
provide a type hint to your parameters. So the above could be reduced to the
following:

.. code-block:: python

    @router.route('profile', '/user/{user.username}')
    def profile(ctx, user: User):
        return 'Hello, %s!' % user.username


.. note::

    The ``user: User`` bit in the function above is a form of function
    parameter annotation - a feature defined in PEP3107_ and accepted for
    python 3.0. A later Python Enhancement Proposal (PEP484_) encourages
    developers to use these bits as type hints.
    
    .. _PEP3107: https://www.python.org/dev/peps/pep-3107/
    .. _PEP484: https://www.python.org/dev/peps/pep-0484/

As long as *User.username* is a table column which has a unique constrint, the
module will implicitly add a ``match2vars`` function that will perform a
database lookup, very similar to the explicit implementation in the previous
code block.

If the *User.username* is not unique, the easiest way is to use a user's id in
the url and keep the username as SEO_:

.. code-block:: python

    @router.route('profile', '/user/{user.username}/{user.id}')
    def profile(ctx, user: User):
        return 'Hello, %s!' % user.username

In this case, the router will also redirect automatically, if the
*user.username* part does not match the attribute of the object. So if you
access the url ``/user/sirlancelot/1`` and the user has changed his username
since this url was generated, the client will receive an HTTP 302 response,
redirecting it to the new url ``/user/loretta/1``.

.. _SEO: https://en.wikipedia.org/wiki/Search_engine_optimization


.. _http_routing:

Request Routing
---------------

We have already seen, that a route is basically just a function with an
additional annotation. We will now look at the application flow from the point
an HTTP request is received to the instant the client receives its response.
Let's first look at the data flow from an abstract perspective:

- :ref:`Create a context <http_routing_ctx>`
- :ref:`Determine Route <http_routing_findroute>`
- :ref:`Call Preroutes <http_routing_preroute>`
- :ref:`Call Route <http_routing_callroute>`


.. _http_routing_ctx:

Request Context
^^^^^^^^^^^^^^^

As soon as an HTTP request is received, the module will first create a new
request :term:`context <context object>` and add a new member called ``http``,
which is an object of type ``HttpContext``. The most prominent two attributes
of this object are *request* and *response*.

The *request* is, of course, the HTTP request that was received. The *response*
object is an instance of :class:`webob.Response`, which will be used to
transmit the server response to the client by default. Usage of this object is
optional, though, as routes may return (or :mod:`raise <webob.exc>`) a
different :class:`webob.Response` object.

The :term:`context <context object>` will be automatically cleaned up at the
end of the request.


.. _http_routing_findroute:

Determining the Route
^^^^^^^^^^^^^^^^^^^^^

Once there is a request context, the router will first determine the route to
call for this request. The following diagram should provide a high-level
overview of this process: 

::

    HTTP request |
                 |
                 +--------------------------------------------+
                 |                     |                      |
                 v                     | no match             | failure
     +----------------------+  found  +------------+  match  +-------------------+
     | Determine next Route |-------->| Test Regex |-------->| Extract Variables |
     +----------------------+         +------------+         +-------------------+
                      |                                                   |
                      | no routes left                            success |
                      v                                                   v
                   +-----+                                         +-------------+
                   | 404 |                                         | route found |
                   +-----+                                         +-------------+
   
   
The details to this process can be found in the section about
:ref:`http_url_conversion`.


.. _http_routing_preroute:

Calling Preroutes
^^^^^^^^^^^^^^^^^

Once we know which route will be called to handle the request, any registered
:term:`preroutes <preroute>` will be called first. A preroute is just a
function that accepts a :term:`context object`, which will be called before the
actual route. They can be used to implement login, access control, or any other
feature independant of the current URL.


.. _http_routing_callroute:

Calling the Route
^^^^^^^^^^^^^^^^^

If the call to the preroutes were successfull, the previously determined route
will now be called. The route has several options for handling the route call. It can:

- return the response body as a string,
- return a `dict` of variables for its template,
- return a :class:`webob.Response` or
- raise a :class:`webob.exc.HTTPException`.

If the route is returning a `dict` of template variables, it should also define
a template in its route declaration:

.. code-block:: python

    @router.route('profile', '/user/{user.username}', tpl='user.jinja2')
    def profile(ctx, user):
        return {
            'user': user
        }

This will implicitly render the template *user.jinja2* with the variables
returned from the route.

.. _http_error_handler:

Error Handlers
--------------

You can configure two types of error handlers, which will be called on certain
conditions:

* HTTP status code handlers will be invoked, when the :term:`route` returns a
  valid response. There can only be one handler per status code. Example for
  registering an error handler, that will print a "pretty error message" on
  exceptions:

  .. code-block:: python

      def handle_exception(ctx):
          return "pretty error message"

  .. code-block:: ini

      [http]
      handler.500 = path.to.handle_exception

  .. note::

      Currently, the router implementation only calls the error handler if
      there actually was an error (i.e. an exception was raised). This is a
      known issue and will be addressed in the future.

* Exception handlers will be invoked, if a :term:`route` raises an exception,
  that is a sub-type of the given exception name:

  .. code-block:: python

      def handle_wrong_answer(ctx):
          return "NO! Yelloooooww ..."

  .. code-block:: ini

      [http]
      handler.WrongAnswerException = path.to.handle_wrong_answer

API
===

.. autofunction:: score.http.init

.. autoclass:: score.http.Route()

    .. automethod:: url

    .. attribute:: callback

        The function to call, when this route is invoked.

.. autoclass:: score.http.ConfiguredHttpModule()

    .. automethod:: route

    .. automethod:: url

    .. automethod:: mkwsgi

