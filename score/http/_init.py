# Copyright © 2015 STRG.AT GmbH, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in the
# file named COPYING.LESSER.txt.
#
# The SCORE Framework and all its parts are distributed without any WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. For more details see the GNU Lesser General Public
# License.
#
# If you have not received a copy of the GNU Lesser General Public License see
# http://www.gnu.org/licenses/.
#
# The License-Agreement realised between you as Licensee and STRG.AT GmbH as
# Licenser including the issue of its valid conclusion and its pre- and
# post-contractual effects is governed by the laws of Austria. Any disputes
# concerning this License-Agreement including the issue of its valid conclusion
# and its pre- and post-contractual effects are exclusively decided by the
# competent court, in whose district STRG.AT GmbH has its registered seat, at
# the discretion of STRG.AT GmbH also the competent court, in whose district the
# Licensee has his registered seat, an establishment or assets.

from ._conf import ConfiguredHttpModule
from score.init import (
    parse_dotted_path, extract_conf, parse_bool, ConfigurationError)
import re


defaults = {
    'debug': False,
}


def init(confdict, ctx):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>` with the following configuration keys:

    :confkey:`router`
        TODO: document me

    :confkey:`handler.*`
        TODO: document me

    :confkey:`debug` :default:`False`
        TODO: document me
    """
    conf = dict(defaults.items())
    conf.update(confdict)
    if 'router' not in conf:
        import score.http
        raise ConfigurationError(score.http, 'No router provided')
    router = parse_dotted_path(conf['router'])
    error_handlers = []
    exception_handlers = []
    for error, handler in extract_conf(conf, 'handler.').items():
        if re.match('\d(\d\d|XX)', error):
            error_handlers[error] = parse_dotted_path(handler)
        else:
            error = parse_dotted_path(error)
            exception_handlers[error] = handler
    debug = parse_bool(conf['debug'])
    return ConfiguredHttpModule(router, error_handlers, exception_handlers,
                                ctx, debug)
