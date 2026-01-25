from .translations import TRANSLATIONS


class I18n:
    def __init__(self, settings):
        self.settings = settings

    def language(self) -> str:
        return self.settings.get("language", "en")

    def set_language(self, lang: str) -> None:
        self.settings.set("language", lang)

    def t(self, key: str | None, **kwargs) -> str:
        if key is None:
            return ""
        lang = self.language()
        text = TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key)
        if text is None:
            text = key
        if not isinstance(text, str):
            text = str(text)
        try:
            return text.format(**kwargs)
        except Exception:
            return text
