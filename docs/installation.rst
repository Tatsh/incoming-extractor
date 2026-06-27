Installation
============

Install from PyPI with your preferred tool:

.. code-block:: shell

   pip install incoming-extractor

Or with `uv <https://docs.astral.sh/uv/>`_:

.. code-block:: shell

   uv tool install incoming-extractor

This installs three console scripts: ``incoming-extractor`` (the main extractor) and the
:doc:`standalone utilities <utilities>` ``ian2obj`` and ``extract-pvr-pack``.

Prerequisites
-------------

Several conversions shell out to native helper programs. They are not bundled and must be available
on ``PATH`` (or pointed at with the matching ``--*-path`` option). See :doc:`native-tools` for the
full list and where to obtain each one. The extractor still runs without them; only the conversions
that need a given helper are skipped, and the affected files are copied verbatim instead.

You also need a copy of the game. Both the PC (Windows) and Sega Dreamcast releases are supported,
as is an installed copy such as the
`Zoom Platform Incoming Trilogy <https://www.zoom-platform.com/product/incoming-trilogy>`_. See
:doc:`usage` for the accepted source types.
