# Colophon

A visual index and identifier for a scanned library.

Built for the **Meta Global AI Developer Hackathon 2026** (Oct 26 – Nov 4), indie track, theme *Build for Your World*.

## What it does

A scanned library is a pile of PDFs with no reliable metadata and, for a large share of them, no text layer at all.
Colophon reads the books the way a cataloguer and an art librarian would:

- **The identifier** reads each book's cover, title page, copyright page and last page with **Muse Spark** and
  produces a catalogue record (title, authors, publisher, year, ISBNs, series and number, language). Every ISBN is
  checksum-tested and the record it resolves to must match the title read from the title page. Verified records are
  written to Calibre; the rest go to a one-click review queue beside the page images.
- **The visual index** segments every illustration, map, plate and photograph on every page with **SAM 3.1**, reads
  each figure and its printed caption with Muse Spark, embeds the result, and serves a search page: a query returns
  the figures, each linking to its page, its caption, and the book's record.

The models from Meta run where they run best: SAM 3.1 locally on the home GPU fleet (two DGX Sparks, an RTX 4090,
an RTX 5080), Muse Spark through the Meta Model API.

## Status

Day 0. Repository created 2026-11-02; submission due 2026-11-04 21:00 ET.

## Layout

To be filled in as the pieces land: coordinator, workers, model adapters, verifier, Calibre writer, search page.

## Demo set

The public demo runs over the Museum of Modern Art's out-of-print exhibition catalogues, which MoMA serves free as
PDFs. The repository ships no scans; the README will list the URLs so the demo set can be rebuilt from scratch.
