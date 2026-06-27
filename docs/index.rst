incoming-extractor
==================

.. include:: badges.rst

Extract and convert assets from the PC and Dreamcast versions of *Incoming* (Rage Software,
published by Interplay, 1998-1999).

Given a PC disc (directory, ISO, or ``DATA1.CAB``), a Dreamcast GDI, or a directory of already
extracted PC or GD-ROM content, ``incoming-extractor`` mirrors the source tree into an output
directory, converting the proprietary assets to open formats and copying everything else verbatim.
The source is never modified.

.. toctree::
   :caption: User guide
   :maxdepth: 2

   installation
   usage
   utilities
   native-tools

.. toctree::
   :caption: Asset formats
   :maxdepth: 2

   formats/index

.. toctree::
   :caption: Reference
   :maxdepth: 2

   api/index
   development

.. only:: html

   Indices and tables
   ------------------

   * :ref:`genindex`
   * :ref:`modindex`
   * :ref:`search`
