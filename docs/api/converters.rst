Converters
==========

Each converter turns one asset format into an open output. The package root re-exports the shared
conversion-rule types, and :mod:`~incoming_extractor.converters.registry` assembles every rule into
the dispatch table.

Shared types
------------

.. automodule:: incoming_extractor.converters
   :members: ConversionError, Rule, UnsupportedFormatError
   :imported-members:

``incoming_extractor.converters.registry``
------------------------------------------

.. automodule:: incoming_extractor.converters.registry
   :members:

``incoming_extractor.converters.images``
----------------------------------------

.. automodule:: incoming_extractor.converters.images
   :members:

``incoming_extractor.converters.models``
----------------------------------------

.. automodule:: incoming_extractor.converters.models
   :members:

``incoming_extractor.converters.models_dc``
-------------------------------------------

.. automodule:: incoming_extractor.converters.models_dc
   :members:

``incoming_extractor.converters.audio``
---------------------------------------

.. automodule:: incoming_extractor.converters.audio
   :members:

``incoming_extractor.converters.sound_dc``
------------------------------------------

.. automodule:: incoming_extractor.converters.sound_dc
   :members:

``incoming_extractor.converters.data``
--------------------------------------

.. automodule:: incoming_extractor.converters.data
   :members:

``incoming_extractor.converters.state``
---------------------------------------

.. automodule:: incoming_extractor.converters.state
   :members:

``incoming_extractor.converters.text``
--------------------------------------

.. automodule:: incoming_extractor.converters.text
   :members:
