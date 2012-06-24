from exceptions import Exception, UnicodeDecodeError, TypeError, KeyError
import logging
import copy
from flexget.plugin import PluginError
from flexget.utils.imdb import extract_id, make_url
from flexget.utils.template import render_from_entry

log = logging.getLogger('entry')


class EntryUnicodeError(Exception):
    """This exception is thrown when trying to set non-unicode compatible field value to entry."""

    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __str__(self):
        return 'Field %s is not unicode-compatible (%r)' % (self.key, self.value)


class LazyField(object):
    """
    LazyField is a type of :class:`Entry` field which is evaluated only
    when it's value is requested. This way FlexGet can avoid doing heavy
    lookups from the internet or database for details that may not be needed
    ever.

    Stores callback function(s) to which populates :class:`Entry` fields.
    Callback is ran when it's called or to get a string representation."""

    def __init__(self, entry, field, func):
        self.entry = entry
        self.field = field
        self.funcs = [func]

    def __call__(self):
        # Return a result from the first lookup function which succeeds
        for func in self.funcs[:]:
            result = func(self.entry, self.field)
            if result is not None:
                return result

    def __str__(self):
        return str(self())

    def __repr__(self):
        return '<LazyField(field=%s)>' % self.field

    def __unicode__(self):
        return unicode(self())


class Entry(dict):
    """
    Represents one item in feed. Must have `url` and *title* fields.

    Stores automatically *original_url* key, which is necessary because
    plugins (eg. urlrewriters) may change *url* into something else
    and otherwise that information would be lost.

    Entry will also transparently convert all ascii strings into unicode
    and raises :class:`EntryUnicodeError` if conversion fails on any value
    being set. Such failures are caught by :class:`~flexget.feed.Feed`
    and trigger :meth:`~flexget.feed.Feed.abort`.
    """

    def __init__(self, *args, **kwargs):
        self.trace = []
        self.snapshots = {}

        if len(args) == 2:
            kwargs['title'] = args[0]
            kwargs['url'] = args[1]
            args = []

        # Make sure constructor does not escape our __setitem__ enforcement
        self.update(*args, **kwargs)

    def __setitem__(self, key, value):
        # Enforce unicode compatibility. Check for all subclasses of basestring, so that NavigableStrings are also cast
        if isinstance(value, basestring) and not type(value) == unicode:
            try:
                value = unicode(value)
            except UnicodeDecodeError:
                raise EntryUnicodeError(key, value)

        # url and original_url handling
        if key == 'url':
            if not isinstance(value, basestring):
                raise PluginError('Tried to set %r url to %r' % (self.get('title'), value))
            self.setdefault('original_url', value)

        # title handling
        if key == 'title':
            if not isinstance(value, basestring):
                raise PluginError('Tried to set title to %r' % value)

        # TODO: HACK! Implement via plugin once #348 (entry events) is implemented
        # enforces imdb_url in same format
        if key == 'imdb_url' and isinstance(value, basestring):
            imdb_id = extract_id(value)
            if imdb_id:
                value = make_url(imdb_id)
            else:
                log.debug('Tried to set imdb_id to invalid imdb url: %s' % value)
                value = None

        try:
            log.trace('ENTRY SET: %s = %r' % (key, value))
        except Exception, e:
            log.debug('trying to debug key `%s` value threw exception: %s' % (key, e))

        dict.__setitem__(self, key, value)

    def update(self, *args, **kwargs):
        """Overridden so our __setitem__ is not avoided."""
        if args:
            if len(args) > 1:
                raise TypeError("update expected at most 1 arguments, got %d" % len(args))
            other = dict(args[0])
            for key in other:
                self[key] = other[key]
        for key in kwargs:
            self[key] = kwargs[key]

    def setdefault(self, key, value=None):
        """Overridden so our __setitem__ is not avoided."""
        if key not in self:
            self[key] = value
        return self[key]

    def __getitem__(self, key):
        """Supports lazy loading of fields. If a stored value is a :class:`LazyField`, call it, return the result."""
        result = dict.__getitem__(self, key)
        if isinstance(result, LazyField):
            log.trace('evaluating lazy field %s' % key)
            return result()
        else:
            return result

    def get(self, key, default=None, eval_lazy=True, lazy=None):
        """
        Overridden so that our __getitem__ gets used for :class:`LazyFields`

        :param string key: Name of the key
        :param object default: Value to be returned if key does not exists
        :param bool eval_lazy: Allow evaluating LazyFields or not
        :param bool lazy: Provided for backwards compatibility
        :return: Value or given *default*
        """
        if lazy is not None:
            log.warning('deprecated lazy kwarg used')
            eval_lazy = lazy
        if not eval_lazy and self.is_lazy(key):
            return default
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        """Will cause lazy field lookup to occur and will return false if a field exists but is None."""
        return self.get(key) is not None

    def register_lazy_fields(self, fields, func):
        """Register a list of fields to be lazily loaded by callback func.

        :param fields:
          List of field names that are registered as lazy fields
        :param func:
          Callback function which is called when lazy field needs to be evaluated.
          Function call will get params (entry, field).
          See :class:`LazyField` class for more details.
        """
        for field in fields:
            if self.is_lazy(field):
                # If the field is already a lazy field, append this function to it's list of functions
                dict.get(self, field).funcs.append(func)
            elif not self.get(field, eval_lazy=False):
                # If it is not a lazy field, and isn't already populated, make it a lazy field
                self[field] = LazyField(self, field, func)

    def unregister_lazy_fields(self, fields, func):
        """
        :param list fields: List of field names to unregister.
          If given field is not lazy loading, value is set to None
        :param function func: Function to be removed from registered.
        :return: Number of removed functions
        :rtype: int
        """
        removed = 0
        for field in fields:
            if self.is_lazy(field):
                lazy_funcs = dict.get(self, field).funcs
                if func in lazy_funcs:
                    removed += 1
                    lazy_funcs.remove(func)
                if not lazy_funcs:
                    self[field] = None
        return removed

    def is_lazy(self, field):
        """
        :param string field: Name of the field to check
        :return: True if field is lazy loading.
        :rtype: bool
        """
        return isinstance(dict.get(self, field), LazyField)

    def safe_str(self):
        return '%s | %s' % (self['title'], self['url'])

    def isvalid(self):
        """
        :return: True if entry is valid. Return False if this cannot be used.
        :rtype: bool
        """
        if not 'title' in self:
            return False
        if not 'url' in self:
            return False
        if not isinstance(self['url'], basestring):
            return False
        if not isinstance(self['title'], basestring):
            return False
        return True

    def take_snapshot(self, name):
        """
        Takes a snapshot of the entry under *name*. Snapshots can be accessed via :attr:`.snapshots`.
        :param string name: Snapshot name
        """
        snapshot = {}
        for field, value in self.iteritems():
            try:
                snapshot[field] = copy.deepcopy(value)
            except TypeError:
                log.warning('Unable to take `%s` snapshot for field `%s` in `%s`' % (name, field, self['title']))
        if snapshot:
            if name in self.snapshots:
                log.warning('Snapshot `%s` is being overwritten for `%s`' % (name, self['title']))
            self.snapshots[name] = snapshot

    def update_using_map(self, field_map, source_item):
        """
        Populates entry fields from a source object using a dictionary that maps from entry field names to
        attributes (or keys) in the source object.

        :param field_map:
          A dictionary mapping entry field names to the attribute in source_item (or keys,
          if source_item is a dict)(nested attributes/dicts are also supported, separated by a dot,)
          or a function that takes source_item as an argument
        :param source_item:
          Source of information to be used by the map
        """
        func = dict.get if isinstance(source_item, dict) else getattr
        for field, value in field_map.iteritems():
            if isinstance(value, basestring):
                self[field] = reduce(func, value.split('.'), source_item)
            else:
                self[field] = value(source_item)

    def render(self, template):
        """
        Renders a template string based on fields in the entry.

        :param string template: A template string that uses jinja2 or python string replacement format.
        :return: The result of the rendering.
        :rtype: string
        :raises RenderError: If there is a problem.
        """
        if not isinstance(template, basestring):
            raise ValueError('Trying to render non string template, got %s' % repr(template))
        log.trace('rendering: %s' % template)
        return render_from_entry(template, self)

    def __eq__(self, other):
        return self.get('title') == other.get('title') and self.get('url') == other.get('url')
