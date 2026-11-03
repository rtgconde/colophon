"""JSON schemas for the structured outputs (strict mode: every property required, no extras)."""

FIGURE_KINDS = ["painting", "photograph", "drawing", "print", "sculpture", "map", "diagram", "illustration",
                "installation", "architecture", "design_object", "film_still", "other"]
PAGE_KINDS = ["plates", "text", "text_with_figures", "index", "front_matter", "advert", "cover", "blank", "other"]

READ_PAGE = {
    "type": "object", "additionalProperties": False,
    "required": ["page_kind", "page_text_language", "figures"],
    "properties": {
        "page_kind": {"type": "string", "enum": PAGE_KINDS},
        "page_text_language": {"type": "string", "description": "ISO 639-1 of the printed text, or empty"},
        "figures": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["k", "is_figure", "kind", "depicts", "caption_found", "caption_text", "artist", "title",
                             "year", "medium", "dimensions", "credit", "is_detail", "notes"],
                "properties": {
                    "k": {"type": "integer", "description": "the box number drawn on the page"},
                    "is_figure": {"type": "boolean", "description": "false when the box holds text, a logo or page furniture"},
                    "kind": {"type": "string", "enum": FIGURE_KINDS},
                    "depicts": {"type": "string", "description": "one sentence, your own words"},
                    "caption_found": {"type": "boolean"},
                    "caption_text": {"type": "string", "description": "the printed caption, verbatim, or empty"},
                    "artist": {"type": "string"}, "title": {"type": "string"}, "year": {"type": "string"},
                    "medium": {"type": "string"}, "dimensions": {"type": "string"},
                    "credit": {"type": "string", "description": "lender, collection or copyright line as printed"},
                    "is_detail": {"type": "boolean"},
                    "notes": {"type": "string"},
                },
            },
        },
    },
}

IDENTIFY_BOOK = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "subtitle", "authors", "editors", "publisher", "place", "year", "edition", "isbns",
                 "series", "series_number", "language", "printing_note", "evidence", "confidence", "notes",
                 "artists", "exhibition_dates"],
    "properties": {
        "title": {"type": "string"}, "subtitle": {"type": "string"},
        "authors": {"type": "array", "items": {"type": "string"}},
        "editors": {"type": "array", "items": {"type": "string"}},
        "publisher": {"type": "string"}, "place": {"type": "string"}, "year": {"type": "string"},
        "edition": {"type": "string"},
        "isbns": {"type": "array", "items": {"type": "string"}, "description": "every ISBN printed, digits and X only"},
        "series": {"type": "string"}, "series_number": {"type": "string"},
        "language": {"type": "string", "description": "ISO 639-1 of the main text"},
        "printing_note": {"type": "string", "description": "the colophon or copyright line, verbatim, or empty"},
        "evidence": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                "required": ["field", "image"],
                                                "properties": {"field": {"type": "string"},
                                                               "image": {"type": "integer",
                                                                         "description": "1-based index of the image the field was read from"}}}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
        "artists": {"type": "array", "items": {"type": "string"},
                    "description": "the artist(s) the exhibition is about, as named on the cover or title page"},
        "exhibition_dates": {"type": "string",
                             "description": "the exhibition's dates as printed (e.g. 'March 5 - May 19, 2003'), or empty"},
    },
}
