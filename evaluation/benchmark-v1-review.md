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

## b1-01

What prevents a custom float converter from injecting a container into the parsed structure?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · single-file · machine-assisted

The wrapper rejects list and dictionary results with ValueError.

The cited implementation supports The wrapper rejects list and dictionary results with ValueError.

- Required point — The wrapper rejects list and dictionary results with ValueError.

- [`src/tomli/_parser.py` 795–801](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L795-L801) · grade 2 · _parser-1 — _parser supplies the first source component needed to establish what prevents a custom float converter from injecting a container into the parsed structure.

- [ ] Independently reviewed

## b1-02

What happens when a key assignment would overwrite an existing value?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · single-file · machine-assisted

The parser raises TOMLDecodeError before assigning the new value.

The cited implementation supports The parser raises TOMLDecodeError before assigning the new value.

- Required point — The parser raises TOMLDecodeError before assigning the new value.

- [`src/tomli/_parser.py` 449–458](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L449-L458) · grade 2 · _parser-1 — _parser supplies the first source component needed to establish what happens when a key assignment would overwrite an existing value.

- [ ] Independently reviewed

## b1-03

How does the file parser handle a stream opened in text mode?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · single-file · machine-assisted

It expects bytes with decode and translates a missing decode method to a binary-mode TypeError.

The cited implementation supports It expects bytes with decode and translates a missing decode method to a binary-mode TypeError.

- Required point — It expects bytes with decode and translates a missing decode method to a binary-mode TypeError.

- [`src/tomli/_parser.py` 152–161](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L152-L161) · grade 2 · _parser-1 — _parser supplies the first source component needed to establish how does the file parser handle a stream opened in text mode.

- [ ] Independently reviewed

## b1-04

Which local time fields default to zero in the converter?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · single-file · machine-assisted

Missing seconds and fractional seconds default to zero.

The cited implementation supports Missing seconds and fractional seconds default to zero.

- Required point — Missing seconds and fractional seconds default to zero.

- [`src/tomli/_re.py` 109–113](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L109-L113) · grade 2 · _re-1 — _re supplies the first source component needed to establish which local time fields default to zero in the converter.

- [ ] Independently reviewed

## b1-05

How does the package expose its binary stream parser and decode the input?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · cross-file · machine-assisted

The initializer imports load from the parser. The implementation decodes UTF-8 before handing text to loads.

The cited implementation supports The initializer imports load from the parser. The implementation decodes UTF-8 before handing text to loads.

- Required point — The initializer imports load from the parser.
- Required point — The implementation decodes UTF-8 before handing text to loads.

- [`src/tomli/__init__.py` 8–8](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/__init__.py#L8-L8) · grade 2 · __init__-1 — __init__ supplies the first source component needed to establish how does the package expose its binary stream parser and decode the input.
- [`src/tomli/_parser.py` 152–161](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L152-L161) · grade 2 · _parser-2 — _parser supplies the additional source component needed to establish how does the package expose its binary stream parser and decode the input.

- [ ] Independently reviewed

## b1-06

How does public error handling expose a parser exception and identify its base class?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · cross-file · machine-assisted

The initializer reexports TOMLDecodeError. The parser defines it as a ValueError subclass.

The cited implementation supports The initializer reexports TOMLDecodeError. The parser defines it as a ValueError subclass.

- Required point — The initializer reexports TOMLDecodeError.
- Required point — The parser defines it as a ValueError subclass.

- [`src/tomli/__init__.py` 5–8](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/__init__.py#L5-L8) · grade 2 · __init__-1 — __init__ supplies the first source component needed to establish how does public error handling expose a parser exception and identify its base class.
- [`src/tomli/_parser.py` 91–94](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L91-L94) · grade 2 · _parser-2 — _parser supplies the additional source component needed to establish how does public error handling expose a parser exception and identify its base class.

- [ ] Independently reviewed

## b1-07

How does numeric dispatch distinguish regular floats from integers?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · cross-file · machine-assisted

The parser passes a match and converter to the number helper. The helper calls the converter for float matches and uses integer conversion otherwise.

The cited implementation supports The parser passes a match and converter to the number helper. The helper calls the converter for float matches and uses integer conversion otherwise.

- Required point — The parser passes a match and converter to the number helper.
- Required point — The helper calls the converter for float matches and uses integer conversion otherwise.

- [`src/tomli/_parser.py` 761–766](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L761-L766) · grade 2 · _parser-1 — _parser supplies the first source component needed to establish how does numeric dispatch distinguish regular floats from integers.
- [`src/tomli/_re.py` 116–119](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L116-L119) · grade 2 · _re-2 — _re supplies the additional source component needed to establish how does numeric dispatch distinguish regular floats from integers.

- [ ] Independently reviewed

## b1-08

How does a date token become a Python object, and where are invalid components handled?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · cross-file · machine-assisted

The regex helper constructs the Python object. The parser wraps conversion ValueError as TOMLDecodeError.

The cited implementation supports The regex helper constructs the Python object. The parser wraps conversion ValueError as TOMLDecodeError.

- Required point — The regex helper constructs the Python object.
- Required point — The parser wraps conversion ValueError as TOMLDecodeError.

- [`src/tomli/_re.py` 59–92](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L59-L92) · grade 2 · _re-1 — _re supplies the first source component needed to establish how does a date token become a Python object, and where are invalid components handled.
- [`src/tomli/_parser.py` 750–756](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L750-L756) · grade 2 · _parser-2 — _parser supplies the additional source component needed to establish how does a date token become a Python object, and where are invalid components handled.

- [ ] Independently reviewed

## b1-09

How are signed timezone offsets produced for parsed datetimes?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · cross-file · machine-assisted

The value parser invokes datetime conversion on the matched token. The conversion module builds a timezone from signed hours and minutes.

The cited implementation supports The value parser invokes datetime conversion on the matched token. The conversion module builds a timezone from signed hours and minutes.

- Required point — The value parser invokes datetime conversion on the matched token.
- Required point — The conversion module builds a timezone from signed hours and minutes.

- [`src/tomli/_parser.py` 750–756](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L750-L756) · grade 2 · _parser-1 — _parser supplies the first source component needed to establish how are signed timezone offsets produced for parsed datetimes.
- [`src/tomli/_re.py` 83–106](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L83-L106) · grade 2 · _re-2 — _re supplies the additional source component needed to establish how are signed timezone offsets produced for parsed datetimes.

- [ ] Independently reviewed

## b1-10

How does custom decimal conversion apply to ordinary numeric tokens and avoid returning containers?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · cross-file · machine-assisted

The numeric helper invokes the supplied converter on the matched float. The parser wraps custom converters to reject dict and list outputs.

The cited implementation supports The numeric helper invokes the supplied converter on the matched float. The parser wraps custom converters to reject dict and list outputs.

- Required point — The numeric helper invokes the supplied converter on the matched float.
- Required point — The parser wraps custom converters to reject dict and list outputs.

- [`src/tomli/_re.py` 116–119](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L116-L119) · grade 2 · _re-1 — _re supplies the first source component needed to establish how does custom decimal conversion apply to ordinary numeric tokens and avoid returning containers.
- [`src/tomli/_parser.py` 783–801](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L783-L801) · grade 2 · _parser-2 — _parser supplies the additional source component needed to establish how does custom decimal conversion apply to ordinary numeric tokens and avoid returning containers.

- [ ] Independently reviewed

## b1-11

How does the grammar for a time token connect to parser dispatch?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · cross-file · machine-assisted

The regex module compiles the local-time pattern. The parser tests that pattern and advances to the end of its match.

The cited implementation supports The regex module compiles the local-time pattern. The parser tests that pattern and advances to the end of its match.

- Required point — The regex module compiles the local-time pattern.
- Required point — The parser tests that pattern and advances to the end of its match.

- [`src/tomli/_re.py` 17–24](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L17-L24) · grade 2 · _re-1 — _re supplies the first source component needed to establish how does the grammar for a time token connect to parser dispatch.
- [`src/tomli/_re.py` 45–45](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L45-L45) · grade 2 · _re-2 — _re supplies the additional source component needed to establish how does the grammar for a time token connect to parser dispatch.
- [`src/tomli/_parser.py` 757–759](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L757-L759) · grade 2 · _parser-3 — _parser supplies the additional source component needed to establish how does the grammar for a time token connect to parser dispatch.

- [ ] Independently reviewed

## b1-12

How do the numeric grammar and parser cooperate before special float handling?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · cross-file · machine-assisted

The regex module defines the ordinary numeric grammar. The parser tries it before the special float branch.

The cited implementation supports The regex module defines the ordinary numeric grammar. The parser tries it before the special float branch.

- Required point — The regex module defines the ordinary numeric grammar.
- Required point — The parser tries it before the special float branch.

- [`src/tomli/_re.py` 26–43](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L26-L43) · grade 2 · _re-1 — _re supplies the first source component needed to establish how do the numeric grammar and parser cooperate before special float handling.
- [`src/tomli/_parser.py` 761–774](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L761-L774) · grade 2 · _parser-2 — _parser supplies the additional source component needed to establish how do the numeric grammar and parser cooperate before special float handling.

- [ ] Independently reviewed

## b1-13

Where is NestedDict defined?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · symbol · machine-assisted

The parser module defines NestedDict.

The cited implementation supports The parser module defines NestedDict.

- Required point — The parser module defines NestedDict.

- [`src/tomli/_parser.py` 293–294](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L293-L294) · grade 2 · _parser-1 — _parser supplies the first source component needed to establish where is NestedDict defined.

- [ ] Independently reviewed

## b1-14

Where is match_to_number defined?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · symbol · machine-assisted

The regular expression conversion module defines match_to_number.

The cited implementation supports The regular expression conversion module defines match_to_number.

- Required point — The regular expression conversion module defines match_to_number.

- [`src/tomli/_re.py` 116–119](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_re.py#L116-L119) · grade 2 · _re-1 — _re supplies the first source component needed to establish where is match_to_number defined.

- [ ] Independently reviewed

## b1-15

Where is parse_inline_table defined?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · symbol · machine-assisted

The parser module contains the inline table parser.

The cited implementation supports The parser module contains the inline table parser.

- Required point — The parser module contains the inline table parser.

- [`src/tomli/_parser.py` 547–550](https://github.com/hukkin/tomli/blob/43a86ade8b795c6ef9b4ec53372a607cd1ed426f/src/tomli/_parser.py#L547-L550) · grade 2 · _parser-1 — _parser supplies the first source component needed to establish where is parse_inline_table defined.

- [ ] Independently reviewed

## b1-16

What median parsing latency did customers see on their production hosts last month?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · insufficient · machine-assisted

The source cannot establish customer production timing.

The source cannot establish customer production timing.



- [ ] Independently reviewed

## b1-17

How many production applications use this exact revision?

hukkin/tomli · `43a86ade8b795c6ef9b4ec53372a607cd1ed426f` · insufficient · machine-assisted

The snapshot contains no production adoption telemetry.

The snapshot contains no production adoption telemetry.



- [ ] Independently reviewed

## b2-01

How are three or more items joined into prose?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · single-file · machine-assisted

The formatter joins all but the last with commas and adds the last item with and.

The cited implementation supports The formatter joins all but the last with commas and adds the last item with and.

- Required point — The formatter joins all but the last with commas and adds the last item with and.

- [`src/humanize/lists.py` 37–40](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/lists.py#L37-L40) · grade 2 · lists-1 — lists supplies the first source component needed to establish how are three or more items joined into prose.

- [ ] Independently reviewed

## b2-02

How does resetting localization affect the current thread?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · single-file · machine-assisted

It assigns None to the thread-local locale.

The cited implementation supports It assigns None to the thread-local locale.

- Required point — It assigns None to the thread-local locale.

- [`src/humanize/i18n.py` 98–100](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L98-L100) · grade 2 · i18n-1 — i18n supplies the first source component needed to establish how does resetting localization affect the current thread.

- [ ] Independently reviewed

## b2-03

What separator does the localization layer fall back to for an unknown decimal locale?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · single-file · machine-assisted

It falls back to a dot.

The cited implementation supports It falls back to a dot.

- Required point — It falls back to a dot.

- [`src/humanize/i18n.py` 207–213](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L207-L213) · grade 2 · i18n-1 — i18n supplies the first source component needed to establish what separator does the localization layer fall back to for an unknown decimal locale.

- [ ] Independently reviewed

## b2-04

What fallback does the localization layer use for thousands grouping?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · single-file · machine-assisted

It falls back to a comma.

The cited implementation supports It falls back to a comma.

- Required point — It falls back to a comma.

- [`src/humanize/i18n.py` 198–204](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L198-L204) · grade 2 · i18n-1 — i18n supplies the first source component needed to establish what fallback does the localization layer use for thousands grouping.

- [ ] Independently reviewed

## b2-05

How does the package make file size formatting available at the top level and where is it implemented?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · cross-file · machine-assisted

The initializer imports naturalsize. The filesize module supplies the formatter and its options.

The cited implementation supports The initializer imports naturalsize. The filesize module supplies the formatter and its options.

- Required point — The initializer imports naturalsize.
- Required point — The filesize module supplies the formatter and its options.

- [`src/humanize/__init__.py` 14–14](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/__init__.py#L14-L14) · grade 2 · __init__-1 — __init__ supplies the first source component needed to establish how does the package make file size formatting available at the top level and where is it implemented.
- [`src/humanize/filesize.py` 39–46](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/filesize.py#L39-L46) · grade 2 · filesize-2 — filesize supplies the additional source component needed to establish how does the package make file size formatting available at the top level and where is it implemented.

- [ ] Independently reviewed

## b2-06

How is iterable formatting exposed as a public package function and implemented?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · cross-file · machine-assisted

The initializer reexports the list formatter. The implementation stringifies items and applies the prose joining rules.

The cited implementation supports The initializer reexports the list formatter. The implementation stringifies items and applies the prose joining rules.

- Required point — The initializer reexports the list formatter.
- Required point — The implementation stringifies items and applies the prose joining rules.

- [`src/humanize/__init__.py` 16–16](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/__init__.py#L16-L16) · grade 2 · __init__-1 — __init__ supplies the first source component needed to establish how is iterable formatting exposed as a public package function and implemented.
- [`src/humanize/lists.py` 32–40](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/lists.py#L32-L40) · grade 2 · lists-2 — lists supplies the additional source component needed to establish how is iterable formatting exposed as a public package function and implemented.

- [ ] Independently reviewed

## b2-07

How does the package expose localization activation and where is the accepted locale passed?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · cross-file · machine-assisted

The initializer imports activate. The localization module defines activate with locale and optional path arguments.

The cited implementation supports The initializer imports activate. The localization module defines activate with locale and optional path arguments.

- Required point — The initializer imports activate.
- Required point — The localization module defines activate with locale and optional path arguments.

- [`src/humanize/__init__.py` 15–15](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/__init__.py#L15-L15) · grade 2 · __init__-1 — __init__ supplies the first source component needed to establish how does the package expose localization activation and where is the accepted locale passed.
- [`src/humanize/i18n.py` 59–64](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L59-L64) · grade 2 · i18n-2 — i18n supplies the additional source component needed to establish how does the package expose localization activation and where is the accepted locale passed.

- [ ] Independently reviewed

## b2-08

How does a large duration group its year count and which formatter supplies the grouping?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · cross-file · machine-assisted

The time formatter substitutes the output of intcomma into the year phrase. The numeric formatter obtains locale separators and groups the digits.

The cited implementation supports The time formatter substitutes the output of intcomma into the year phrase. The numeric formatter obtains locale separators and groups the digits.

- Required point — The time formatter substitutes the output of intcomma into the year phrase.
- Required point — The numeric formatter obtains locale separators and groups the digits.

- [`src/humanize/time.py` 257–257](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/time.py#L257-L257) · grade 2 · time-1 — time supplies the first source component needed to establish how does a large duration group its year count and which formatter supplies the grouping.
- [`src/humanize/number.py` 180–181](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/number.py#L180-L181) · grade 2 · number-2 — number supplies the additional source component needed to establish how does a large duration group its year count and which formatter supplies the grouping.
- [`src/humanize/number.py` 198–204](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/number.py#L198-L204) · grade 2 · number-3 — number supplies the additional source component needed to establish how does a large duration group its year count and which formatter supplies the grouping.

- [ ] Independently reviewed

## b2-09

How is the unit wording chosen for a compact large number?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · cross-file · machine-assisted

The number formatter calls the pluralization helper with its rounded quantity. The localization module dispatches pluralization through the translation object.

The cited implementation supports The number formatter calls the pluralization helper with its rounded quantity. The localization module dispatches pluralization through the translation object.

- Required point — The number formatter calls the pluralization helper with its rounded quantity.
- Required point — The localization module dispatches pluralization through the translation object.

- [`src/humanize/number.py` 294–299](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/number.py#L294-L299) · grade 2 · number-1 — number supplies the first source component needed to establish how is the unit wording chosen for a compact large number.
- [`src/humanize/i18n.py` 131–143](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L131-L143) · grade 2 · i18n-2 — i18n supplies the additional source component needed to establish how is the unit wording chosen for a compact large number.

- [ ] Independently reviewed

## b2-10

How does the relative calendar-day formatter translate the label for today?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · cross-file · machine-assisted

The calendar formatter selects the today label for a zero-day difference. The localization helper resolves the message through the active translation.

The cited implementation supports The calendar formatter selects the today label for a zero-day difference. The localization helper resolves the message through the active translation.

- Required point — The calendar formatter selects the today label for a zero-day difference.
- Required point — The localization helper resolves the message through the active translation.

- [`src/humanize/time.py` 349–352](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/time.py#L349-L352) · grade 2 · time-1 — time supplies the first source component needed to establish how does the relative calendar-day formatter translate the label for today.
- [`src/humanize/i18n.py` 103–112](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L103-L112) · grade 2 · i18n-2 — i18n supplies the additional source component needed to establish how does the relative calendar-day formatter translate the label for today.

- [ ] Independently reviewed

## b2-11

How is a small number converted to a word and localized?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · cross-file · machine-assisted

The numeric formatter looks up the word and invokes the translation helper. The helper delegates to the active gettext catalog.

The cited implementation supports The numeric formatter looks up the word and invokes the translation helper. The helper delegates to the active gettext catalog.

- Required point — The numeric formatter looks up the word and invokes the translation helper.
- Required point — The helper delegates to the active gettext catalog.

- [`src/humanize/number.py` 335–340](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/number.py#L335-L340) · grade 2 · number-1 — number supplies the first source component needed to establish how is a small number converted to a word and localized.
- [`src/humanize/i18n.py` 103–112](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L103-L112) · grade 2 · i18n-2 — i18n supplies the additional source component needed to establish how is a small number converted to a word and localized.

- [ ] Independently reviewed

## b2-12

How do long precise durations combine translated units and grouped integer counts?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · cross-file · machine-assisted

The duration formatter pluralizes unit wording and inserts the grouped number. The thousands grouping is supplied by the separate number formatter.

The cited implementation supports The duration formatter pluralizes unit wording and inserts the grouped number. The thousands grouping is supplied by the separate number formatter.

- Required point — The duration formatter pluralizes unit wording and inserts the grouped number.
- Required point — The thousands grouping is supplied by the separate number formatter.

- [`src/humanize/time.py` 656–666](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/time.py#L656-L666) · grade 2 · time-1 — time supplies the first source component needed to establish how do long precise durations combine translated units and grouped integer counts.
- [`src/humanize/number.py` 198–204](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/number.py#L198-L204) · grade 2 · number-2 — number supplies the additional source component needed to establish how do long precise durations combine translated units and grouped integer counts.

- [ ] Independently reviewed

## b2-13

Where is scientific defined?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · symbol · machine-assisted

The number module defines the scientific notation formatter.

The cited implementation supports The number module defines the scientific notation formatter.

- Required point — The number module defines the scientific notation formatter.

- [`src/humanize/number.py` 414–415](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/number.py#L414-L415) · grade 2 · number-1 — number supplies the first source component needed to establish where is scientific defined.

- [ ] Independently reviewed

## b2-14

Where is precisedelta defined?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · symbol · machine-assisted

The time module defines precisedelta.

The cited implementation supports The time module defines precisedelta.

- Required point — The time module defines precisedelta.

- [`src/humanize/time.py` 476–482](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/time.py#L476-L482) · grade 2 · time-1 — time supplies the first source component needed to establish where is precisedelta defined.

- [ ] Independently reviewed

## b2-15

Where is _pgettext defined?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · symbol · machine-assisted

The localization module defines the context-aware translation helper.

The cited implementation supports The localization module defines the context-aware translation helper.

- Required point — The localization module defines the context-aware translation helper.

- [`src/humanize/i18n.py` 115–119](https://github.com/python-humanize/humanize/blob/a95004512dde4e8f0269946bb4af754382347441/src/humanize/i18n.py#L115-L119) · grade 2 · i18n-1 — i18n supplies the first source component needed to establish where is _pgettext defined.

- [ ] Independently reviewed

## b2-16

How many production users switched their locale to French last week?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · insufficient · machine-assisted

Usage telemetry would be required to answer.

Usage telemetry would be required to answer.



- [ ] Independently reviewed

## b2-17

Which production host has the fastest duration formatting?

python-humanize/humanize · `a95004512dde4e8f0269946bb4af754382347441` · insufficient · machine-assisted

Deployment measurements are needed and unavailable from the code.

Deployment measurements are needed and unavailable from the code.



- [ ] Independently reviewed

## b3-01

How does the timezone object compute a negative UTC offset?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · single-file · machine-assisted

It stores a negative sign for a minus offset and applies it to the timedelta.

The cited implementation supports It stores a negative sign for a minus offset and applies it to the timedelta.

- Required point — It stores a negative sign for a minus offset and applies it to the timedelta.

- [`toml/tz.py` 5–12](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/tz.py#L5-L12) · grade 2 · tz-1 — tz supplies the first source component needed to establish how does the timezone object compute a negative UTC offset.
- [`toml/tz.py` 23–24](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/tz.py#L23-L24) · grade 2 · tz-2 — tz supplies the additional source component needed to establish how does the timezone object compute a negative UTC offset.

- [ ] Independently reviewed

## b3-02

What offset text represents Z inside the timezone object?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · single-file · machine-assisted

The constructor normalizes Z to the string +00:00.

The cited implementation supports The constructor normalizes Z to the string +00:00.

- Required point — The constructor normalizes Z to the string +00:00.

- [`toml/tz.py` 5–9](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/tz.py#L5-L9) · grade 2 · tz-1 — tz supplies the first source component needed to establish what offset text represents Z inside the timezone object.

- [ ] Independently reviewed

## b3-03

How does the timezone object report daylight savings?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · single-file · machine-assisted

The dst method always returns a zero timedelta.

The cited implementation supports The dst method always returns a zero timedelta.

- Required point — The dst method always returns a zero timedelta.

- [`toml/tz.py` 26–27](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/tz.py#L26-L27) · grade 2 · tz-1 — tz supplies the first source component needed to establish how does the timezone object report daylight savings.

- [ ] Independently reviewed

## b3-04

How does the file serializer handle a missing write capability?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · single-file · machine-assisted

It checks the destination write member and raises TypeError when the member is falsey.

The cited implementation supports It checks the destination write member and raises TypeError when the member is falsey.

- Required point — It checks the destination write member and raises TypeError when the member is falsey.

- [`toml/encoder.py` 27–28](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/encoder.py#L27-L28) · grade 2 · encoder-1 — encoder supplies the first source component needed to establish how does the file serializer handle a missing write capability.

- [ ] Independently reviewed

## b3-05

How does top-level text serialization connect to traversal of nested sections?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · cross-file · machine-assisted

The initializer assigns dumps from the encoder module. The encoder repeatedly serializes queued sections and collects nested sections.

The cited implementation supports The initializer assigns dumps from the encoder module. The encoder repeatedly serializes queued sections and collects nested sections.

- Required point — The initializer assigns dumps from the encoder module.
- Required point — The encoder repeatedly serializes queued sections and collects nested sections.

- [`toml/__init__.py` 19–19](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/__init__.py#L19-L19) · grade 2 · __init__-1 — __init__ supplies the first source component needed to establish how does top-level text serialization connect to traversal of nested sections.
- [`toml/encoder.py` 60–81](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/encoder.py#L60-L81) · grade 2 · encoder-2 — encoder supplies the additional source component needed to establish how does top-level text serialization connect to traversal of nested sections.

- [ ] Independently reviewed

## b3-06

How do callers obtain the public string parser and which component provides its initial mapping?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · cross-file · machine-assisted

The initializer exposes decoder.loads. The decoder constructs a decoder if needed and asks it for an empty table.

The cited implementation supports The initializer exposes decoder.loads. The decoder constructs a decoder if needed and asks it for an empty table.

- Required point — The initializer exposes decoder.loads.
- Required point — The decoder constructs a decoder if needed and asks it for an empty table.

- [`toml/__init__.py` 13–13](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/__init__.py#L13-L13) · grade 2 · __init__-1 — __init__ supplies the first source component needed to establish how do callers obtain the public string parser and which component provides its initial mapping.
- [`toml/decoder.py` 165–185](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/decoder.py#L165-L185) · grade 2 · decoder-2 — decoder supplies the additional source component needed to establish how do callers obtain the public string parser and which component provides its initial mapping.

- [ ] Independently reviewed

## b3-07

How is the named public decode exception connected to its implementation?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · cross-file · machine-assisted

The initializer exposes decoder.TomlDecodeError. The decoder defines it as a ValueError and derives positional details.

The cited implementation supports The initializer exposes decoder.TomlDecodeError. The decoder defines it as a ValueError and derives positional details.

- Required point — The initializer exposes decoder.TomlDecodeError.
- Required point — The decoder defines it as a ValueError and derives positional details.

- [`toml/__init__.py` 15–15](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/__init__.py#L15-L15) · grade 2 · __init__-1 — __init__ supplies the first source component needed to establish how is the named public decode exception connected to its implementation.
- [`toml/decoder.py` 50–66](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/decoder.py#L50-L66) · grade 2 · decoder-2 — decoder supplies the additional source component needed to establish how is the named public decode exception connected to its implementation.

- [ ] Independently reviewed

## b3-08

How is an explicit UTC offset on a decoded datetime represented?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · cross-file · machine-assisted

The decoder constructs a TomlTz and attaches it to the datetime. The timezone class parses sign, hours and minutes and returns a signed timedelta.

The cited implementation supports The decoder constructs a TomlTz and attaches it to the datetime. The timezone class parses sign, hours and minutes and returns a signed timedelta.

- Required point — The decoder constructs a TomlTz and attaches it to the datetime.
- Required point — The timezone class parses sign, hours and minutes and returns a signed timedelta.

- [`toml/decoder.py` 539–554](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/decoder.py#L539-L554) · grade 2 · decoder-1 — decoder supplies the first source component needed to establish how is an explicit UTC offset on a decoded datetime represented.
- [`toml/tz.py` 5–12](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/tz.py#L5-L12) · grade 2 · tz-2 — tz supplies the additional source component needed to establish how is an explicit UTC offset on a decoded datetime represented.
- [`toml/tz.py` 23–24](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/tz.py#L23-L24) · grade 2 · tz-3 — tz supplies the additional source component needed to establish how is an explicit UTC offset on a decoded datetime represented.

- [ ] Independently reviewed

## b3-09

How is an inline table kept recognizable when it is serialized again?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · cross-file · machine-assisted

The decoder creates a mapping subclass tagged as InlineTableDict. The encoder recognizes that marker when preservation is enabled and emits an inline table.

The cited implementation supports The decoder creates a mapping subclass tagged as InlineTableDict. The encoder recognizes that marker when preservation is enabled and emits an inline table.

- Required point — The decoder creates a mapping subclass tagged as InlineTableDict.
- Required point — The encoder recognizes that marker when preservation is enabled and emits an inline table.

- [`toml/decoder.py` 631–652](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/decoder.py#L631-L652) · grade 2 · decoder-1 — decoder supplies the first source component needed to establish how is an inline table kept recognizable when it is serialized again.
- [`toml/encoder.py` 227–230](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/encoder.py#L227-L230) · grade 2 · encoder-2 — encoder supplies the additional source component needed to establish how is an inline table kept recognizable when it is serialized again.

- [ ] Independently reviewed

## b3-10

How does the ordered decoder affect the mapping used by text parsing?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · cross-file · machine-assisted

The ordered subclass supplies OrderedDict to the base decoder. The base decoder stores that factory and uses it to create tables.

The cited implementation supports The ordered subclass supplies OrderedDict to the base decoder. The base decoder stores that factory and uses it to create tables.

- Required point — The ordered subclass supplies OrderedDict to the base decoder.
- Required point — The base decoder stores that factory and uses it to create tables.

- [`toml/ordered.py` 6–9](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/ordered.py#L6-L9) · grade 2 · ordered-1 — ordered supplies the first source component needed to establish how does the ordered decoder affect the mapping used by text parsing.
- [`toml/decoder.py` 635–642](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/decoder.py#L635-L642) · grade 2 · decoder-2 — decoder supplies the additional source component needed to establish how does the ordered decoder affect the mapping used by text parsing.

- [ ] Independently reviewed

## b3-11

How does the ordered encoder choose its mapping type for new sections?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · cross-file · machine-assisted

The ordered subclass passes OrderedDict to the base encoder. The base encoder stores the mapping factory and uses it for empty tables.

The cited implementation supports The ordered subclass passes OrderedDict to the base encoder. The base encoder stores the mapping factory and uses it for empty tables.

- Required point — The ordered subclass passes OrderedDict to the base encoder.
- Required point — The base encoder stores the mapping factory and uses it for empty tables.

- [`toml/ordered.py` 12–15](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/ordered.py#L12-L15) · grade 2 · ordered-1 — ordered supplies the first source component needed to establish how does the ordered encoder choose its mapping type for new sections.
- [`toml/encoder.py` 129–149](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/encoder.py#L129-L149) · grade 2 · encoder-2 — encoder supplies the additional source component needed to establish how does the ordered encoder choose its mapping type for new sections.

- [ ] Independently reviewed

## b3-12

How does a caller enable the public inline-preserving encoder and what does it configure?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · cross-file · machine-assisted

The initializer exposes TomlPreserveInlineDictEncoder. The subclass initializes the base encoder with preservation enabled.

The cited implementation supports The initializer exposes TomlPreserveInlineDictEncoder. The subclass initializes the base encoder with preservation enabled.

- Required point — The initializer exposes TomlPreserveInlineDictEncoder.
- Required point — The subclass initializes the base encoder with preservation enabled.

- [`toml/__init__.py` 22–22](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/__init__.py#L22-L22) · grade 2 · __init__-1 — __init__ supplies the first source component needed to establish how does a caller enable the public inline-preserving encoder and what does it configure.
- [`toml/encoder.py` 236–240](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/encoder.py#L236-L240) · grade 2 · encoder-2 — encoder supplies the additional source component needed to establish how does a caller enable the public inline-preserving encoder and what does it configure.

- [ ] Independently reviewed

## b3-13

Where is TomlNumpyEncoder implemented?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · symbol · machine-assisted

The encoder module defines TomlNumpyEncoder.

The cited implementation supports The encoder module defines TomlNumpyEncoder.

- Required point — The encoder module defines TomlNumpyEncoder.

- [`toml/encoder.py` 270–273](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/encoder.py#L270-L273) · grade 2 · encoder-1 — encoder supplies the first source component needed to establish where is TomlNumpyEncoder implemented.

- [ ] Independently reviewed

## b3-14

Where is TomlPreserveCommentDecoder implemented?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · symbol · machine-assisted

The decoder module defines TomlPreserveCommentDecoder.

The cited implementation supports The decoder module defines TomlPreserveCommentDecoder.

- Required point — The decoder module defines TomlPreserveCommentDecoder.

- [`toml/decoder.py` 1036–1039](https://github.com/uiri/toml/blob/65bab7582ce14c55cdeec2244c65ea23039c9e6f/toml/decoder.py#L1036-L1039) · grade 2 · decoder-1 — decoder supplies the first source component needed to establish where is TomlPreserveCommentDecoder implemented.

- [ ] Independently reviewed

## b3-15

How many users serialized documents with this library last month?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · insufficient · machine-assisted

The source snapshot provides no usage metrics.

The source snapshot provides no usage metrics.



- [ ] Independently reviewed

## b3-16

Which organization has the largest TOML file parsed by this revision in production?

uiri/toml · `65bab7582ce14c55cdeec2244c65ea23039c9e6f` · insufficient · machine-assisted

The source does not contain a production workload inventory.

The source does not contain a production workload inventory.



- [ ] Independently reviewed
