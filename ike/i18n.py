"""Interface translations. Source strings are English."""

import locale
import os

_lang = "en"
_pack = {}          # strings of a downloaded language pack (when one is active)


def pack_dir():
    from .osinfo import app_dir
    return app_dir("data") / "lang"


def shipped_dir():
    from .config import RES_DIR
    return RES_DIR / "lang"


def installed_packs():
    """[(code, name)] of the available languages: shipped with I.K.E. or added by the user."""
    import json
    found = {}
    for d in (shipped_dir(), pack_dir()):
        if d.is_dir():
            for f in sorted(d.glob("*.json")):
                try:
                    found[f.stem] = json.loads(f.read_text("utf-8")).get("name") or f.stem
                except (OSError, ValueError):
                    continue
    return sorted(found.items(), key=lambda kv: kv[1].lower())


def install_pack(data):
    """Validate and store a language pack (bytes or str of JSON). Returns its code."""
    import json
    import re
    obj = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    code = str(obj.get("code", "")).strip()
    strings = obj.get("strings")
    if not re.fullmatch(r"[A-Za-z]{2,3}([_-][A-Za-z0-9]{2,8})?", code) or not isinstance(strings, dict):
        raise ValueError("not an I.K.E. language pack")
    clean = {k: v for k, v in strings.items() if isinstance(k, str) and isinstance(v, str) and v}
    # a translation must keep the same placeholders as the original text
    clean = {k: v for k, v in clean.items()
             if sorted(re.findall(r"%[sd%]", k)) == sorted(re.findall(r"%[sd%]", v))}
    pack_dir().mkdir(parents=True, exist_ok=True)
    (pack_dir() / (code + ".json")).write_text(json.dumps(
        {"code": code, "name": str(obj.get("name") or code), "strings": clean},
        ensure_ascii=False, indent=0), "utf-8")
    return code


def template():
    """Every interface string, for translators (see docs/TRANSLATING.md).

    The Italian pack is the reference: it holds every string of the interface."""
    import json
    return sorted(json.loads((shipped_dir() / "it.json").read_text("utf-8"))["strings"])


def _load_pack(code):
    import json
    import re
    if not re.fullmatch(r"[A-Za-z]{2,3}([_-][A-Za-z0-9]{2,8})?", code or ""):
        return None
    for d in (pack_dir(), shipped_dir()):          # the user's own pack wins
        try:
            return json.loads((d / (code + ".json")).read_text("utf-8"))["strings"]
        except (OSError, ValueError, KeyError):
            continue
    return None


def setup(choice="auto"):
    global _lang, _pack
    _pack = {}
    if choice == "en":
        _lang = choice
        return
    if choice and choice != "auto":
        strings = _load_pack(choice)
        if strings is not None:
            _lang, _pack = choice, strings
            return
    code = (os.environ.get("LANGUAGE") or os.environ.get("LC_ALL")
            or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "")
    if not code:
        try:
            code = locale.getlocale()[0] or ""
        except Exception:
            code = ""
    short = code.split(":")[0].split(".")[0].replace("-", "_").split("_")[0].lower()
    if short and short != "en" and _load_pack(short) is not None:
        _lang, _pack = short, _load_pack(short)
    else:
        _lang = "en"


def current():
    return _lang


def T(text):
    if _pack:
        return _pack.get(text, text)
    return text
