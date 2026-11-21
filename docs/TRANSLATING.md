# Translating I.K.E.

Interface strings are written in English in the source. Every language,
Italian included, is a JSON file in `ike/resources/lang/`:

```json
{
  "code": "es",
  "name": "Español",
  "strings": { "Settings": "Ajustes", "Downloads": "Descargas" }
}
```

- `code` is the language code (`es`, `pt`, `zh`, `zh_TW` …); the file is named
  after it.
- `strings` maps each English string to its translation. Missing strings are
  shown in English.
- Keep placeholders (`%s`, `%d`, `{url}`, `{lang}`), the `&` accelerator in menu
  names and the final `…` or `:` exactly as in the original.

The Italian pack (`it.json`) is the reference list: a new string in the source
must be added there too, and `template()` and `tools/check-lang.py` take the
list of strings from it. The list of all strings can be printed with:

```bash
python3 -c "import sys; sys.path.insert(0, '.'); from ike.i18n import template; print(*template(), sep='\n')"
```

Check a pack (missing strings, placeholders, `&`, final `…` / `:`) with:

```bash
python3 tools/check-lang.py zh ja
```

A translation longer than the English text is fine: buttons grow, long
texts wrap. Check that every text of the pack fits the interface with
`IKE_FIT_LANGS=es python3 -m pytest tests/test_text_fit.py` (the language
codes separated by commas; without the variable, every pack).

Users can also add a language pack from a file in Settings → Language; it is
stored in `~/.local/share/ike-browser/lang/` and takes precedence over the
bundled one.
