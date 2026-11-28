# Annotation review

Check each expected answer and span against the pinned source. Record corrections in a new dataset version after a freeze.

## dev-1

How does the text parser normalize Windows line endings?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · single-file · machine-assisted

It replaces CRLF pairs with LF before parsing.

Machine-assisted annotation of the pinned implementation.

- Required point — It replaces CRLF pairs with LF before parsing.

- [`src/tomli/_parser.py` 164–170](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L164-L170) · grade 2 · component-1 — Implementation or public API binding for the stated behavior.

- [ ] Independently reviewed

## dev-2

How is a standalone time literal turned into a Python time value?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · cross-file · machine-assisted

The parser matches a local-time token and delegates conversion. The helper converts the components, defaults missing seconds and fractions to zero, and pads fractional seconds to microseconds.

Machine-assisted annotation of the pinned implementation.

- Required point — The parser matches a local-time token and delegates conversion. The helper converts the components, defaults missing seconds and fractions to zero, and pads fractional seconds to microseconds.

- [`src/tomli/_parser.py` 757–759](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L757-L759) · grade 2 · component-1 — Implementation or public API binding for the stated behavior.
- [`src/tomli/_re.py` 109–113](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L109-L113) · grade 2 · component-2 — Implementation or public API binding for the stated behavior.

- [ ] Independently reviewed

## dev-3

Where is cached_tz implemented?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · symbol · machine-assisted

The fixed-offset timezone helper is defined in the regular expression conversion module.

Machine-assisted annotation of the pinned implementation.

- Required point — The fixed-offset timezone helper is defined in the regular expression conversion module.

- [`src/tomli/_re.py` 99–106](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L99-L106) · grade 2 · component-1 — Implementation or public API binding for the stated behavior.

- [ ] Independently reviewed

## dev-4

How are empty and one-element iterables handled by the natural list formatter?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · single-file · machine-assisted

The formatter stringifies the items, returns an empty string for no items, and returns the sole string unchanged for one item.

Machine-assisted annotation of the pinned implementation.

- Required point — The formatter stringifies the items, returns an empty string for no items, and returns the sole string unchanged for one item.

- [`src/humanize/lists.py` 32–36](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/lists.py#L32-L36) · grade 2 · component-1 — Implementation or public API binding for the stated behavior.

- [ ] Independently reviewed

## dev-5

How does numeric grouping choose the separators, and what are their defaults?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · cross-file · machine-assisted

The number formatter calls localization helpers for the thousands and decimal separators. Those helpers look up the calling thread’s locale and default to comma and dot respectively.

Machine-assisted annotation of the pinned implementation.

- Required point — The number formatter calls localization helpers for the thousands and decimal separators. Those helpers look up the calling thread’s locale and default to comma and dot respectively.

- [`src/humanize/number.py` 180–181](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/number.py#L180-L181) · grade 2 · component-1 — Implementation or public API binding for the stated behavior.
- [`src/humanize/i18n.py` 198–213](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L198-L213) · grade 2 · component-2 — Implementation or public API binding for the stated behavior.

- [ ] Independently reviewed

## dev-6

Where is deactivate implemented?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · symbol · machine-assisted

The localization module defines it and clears the calling thread’s active locale.

Machine-assisted annotation of the pinned implementation.

- Required point — The localization module defines it and clears the calling thread’s active locale.

- [`src/humanize/i18n.py` 98–100](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L98-L100) · grade 2 · component-1 — Implementation or public API binding for the stated behavior.

- [ ] Independently reviewed

## dev-7

What does the file-based serializer return after writing?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · single-file · machine-assisted

It calls the string serializer, writes that string to the destination, and returns the same string.

Machine-assisted annotation of the pinned implementation.

- Required point — It calls the string serializer, writes that string to the destination, and returns the same string.

- [`toml/encoder.py` 27–31](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/encoder.py#L27-L31) · grade 2 · component-1 — Implementation or public API binding for the stated behavior.

- [ ] Independently reviewed

## dev-8

How does the package make serialization to a file available at its top level?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · cross-file · machine-assisted

The package initializer exposes the encoder module’s dump function. The encoder writes and returns the serialized string.

Machine-assisted annotation of the pinned implementation.

- Required point — The package initializer exposes the encoder module’s dump function. The encoder writes and returns the serialized string.

- [`toml/__init__.py` 18–18](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/__init__.py#L18-L18) · grade 2 · component-1 — Implementation or public API binding for the stated behavior.
- [`toml/encoder.py` 27–31](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/encoder.py#L27-L31) · grade 2 · component-2 — Implementation or public API binding for the stated behavior.

- [ ] Independently reviewed

## dev-9

Where is TomlTz defined?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · symbol · machine-assisted

It is defined in the timezone module as a tzinfo subclass.

Machine-assisted annotation of the pinned implementation.

- Required point — It is defined in the timezone module as a tzinfo subclass.

- [`toml/tz.py` 1–5](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/tz.py#L1-L5) · grade 2 · component-1 — Implementation or public API binding for the stated behavior.

- [ ] Independently reviewed
