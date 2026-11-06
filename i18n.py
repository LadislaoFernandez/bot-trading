"""Textos en español (idioma base) e inglés.

t("Texto en español", var=...) devuelve el texto en el idioma elegido, con las variables ya reemplazadas.
Si falta una traducción, se muestra el texto en español.
"""
LANG = "es"


def set_lang(lang):
    global LANG
    LANG = lang if lang in ("es", "en") else "es"


def t(_texto, /, **kw):
    if LANG == "en":
        _texto = EN.get(_texto, _texto)
    return _texto.format(**kw) if kw else _texto


def num(v, d=2, signo=False):
    """Número con el formato del idioma: 1.234,56 (es) o 1,234.56 (en)."""
    if v is None:
        return "—"
    v = round(v, d)
    if v == 0:
        v = 0.0
    s = f"{abs(v):,.{d}f}"
    if LANG != "en":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    if v < 0:
        return "−" + s
    return ("+" + s) if signo and v > 0 else s


EN = {}  # se completa en i18n_en.py

try:
    from i18n_en import EN as _EN
    EN.update(_EN)
except ImportError:
    pass
