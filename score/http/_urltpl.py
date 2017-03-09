# Copyright © 2015-2017 STRG.AT GmbH, Vienna, Austria
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

import abc
import re
import urllib


class UrlGenerationException(Exception):
    pass


class MissingVariable(UrlGenerationException, KeyError):
    pass


class InvalidVariable(UrlGenerationException, ValueError):
    pass


class UrlTemplate(abc.ABC):

    @property
    def regex(self):
        if not hasattr(self, '__regex'):
            self.__regex = self._to_regex()
        return self.__regex

    def match2vars(self, ctx, match):
        return dict((var, match.group(var)) for var in self.variables)

    @property
    @abc.abstractmethod
    def variables(self):
        pass

    @abc.abstractmethod
    def _to_regex(self):
        pass

    @abc.abstractmethod
    def __lt__(self, other):
        pass

    @abc.abstractmethod
    def equals(self, other):
        pass


class StaticUrl(UrlTemplate):

    def __init__(self, string):
        self.string = string

    @property
    def variables(self):
        return []

    def _to_regex(self):
        return re.compile(re.escape(self.string))

    def __lt__(self, other):
        if isinstance(other, PatternUrlTemplate):
            return True
        if isinstance(other, StaticUrl):
            return self.string < other.string
        return NotImplemented

    def equals(self, other):
        if self is other:
            return True
        if not isinstance(other, UrlTemplate):
            return False
        if self.regex.pattern == other.regex.pattern:
            return True
        return False


class PatternUrlPart:

    def __init__(self, is_regex, pattern, variable=None):
        self.is_regex = is_regex
        self.pattern = pattern
        self.variable = variable

    def __repr__(self):
        return 'UrlPart(pattern=%s)' % (self.pattern)


class PatternUrlTemplate(UrlTemplate):

    def __init__(self, pattern):
        super().__init__()
        if not pattern:
            pattern = '/'
        elif pattern[0] != '/':
            pattern = '/' + pattern
        self.pattern = pattern
        self.parts = []
        self._regex_pattern = ''
        self._var2regex = {}
        self._regexname2var = {}
        for match in re.finditer(r'[^{]+|\{.+?\}', pattern):
            part = match.group(0)
            if part[0] != '{':
                self.parts.append(PatternUrlPart(0, part))
                self._regex_pattern += re.escape(part)
                continue
            if '>' in part:
                name, pattern = part[1:-1].split('>', 1)
            else:
                name = part[1:-1]
                pattern = '[^/]+'
            self._var2regex[name] = re.compile(pattern)
            self.parts.append(PatternUrlPart(10, pattern, name))
            re_name = self._mkregexname(name)
            self._regex_pattern += '(?P<%s>%s)' % (re_name, pattern)
        self._regex_pattern += '$'

    def match2vars(self, ctx, match):
        return dict((var, match.group(name))
                    for name, var in self._regexname2var.items())

    def _mkregexname(self, name):
        re_name = re.sub(r'[^a-z0-9_]', '_', name)
        if re_name in self._regexname2var:
            i = 1
            new_name = re_name + '_1'
            while new_name in self._regexname2var:
                i += 1
                new_name = re_name + '_' + i
            re_name = new_name
        self._regexname2var[re_name] = name
        return re_name

    @property
    def variables(self):
        return list(self._var2regex.keys())

    def generate(self, **kwargs):
        for var, regex in self._var2regex.items():
            if var not in kwargs:
                raise MissingVariable(var)
            kwargs[var] = str(kwargs[var])
            if not regex.match(kwargs[var]):
                raise InvalidVariable(
                    'Value for "%s" does not match variable\'s regex (%s)' %
                    (var, regex.pattern))
        url = ''
        for part in self.parts:
            if part.variable:
                url += urllib.parse.quote(kwargs[part.variable])
            else:
                url += part.pattern
        return url

    def _to_regex(self):
        return re.compile(self._regex_pattern)

    def __str__(self):
        result = ''
        for part in self.parts:
            if part.variable:
                result += '{%s}' % part.variable
            else:
                result += part.pattern
        return result

    def __repr__(self):
        return 'PatternUrlTemplate(%s)' % self.pattern

    def __lt__(self, other):
        if not isinstance(other, PatternUrlTemplate):
            return NotImplemented
        for i in range(min(len(self.parts), len(other.parts))):
            mypart = self.parts[i]
            hispart = other.parts[i]
            if not mypart.is_regex and not hispart.is_regex:
                if mypart.pattern == hispart.pattern:
                    continue
                if mypart.pattern.startswith(hispart.pattern):
                    return True
                if hispart.pattern.startswith(mypart.pattern):
                    return False
                return mypart.pattern < hispart.pattern
            if not mypart.is_regex and hispart.is_regex:
                return True
            if mypart.is_regex and not hispart.is_regex:
                return False
        return len(self.parts) > len(other.parts)

    def equals(self, other):
        if self is other:
            return True
        if not isinstance(other, UrlTemplate):
            return False
        if self.regex.pattern == other.regex.pattern:
            return True
        if not isinstance(other, PatternUrlTemplate):
            return False
        if len(self.parts) != len(other.parts):
            return False
        for i in range(len(self.parts)):
            mypart = self.parts[i]
            otherpart = other.parts[i]
            if mypart.is_regex != otherpart.is_regex:
                return False
            if mypart.pattern != otherpart.pattern:
                return False
        return True
