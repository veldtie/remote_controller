from .translations import TRANSLATIONS


class I18n:
    def __init__(self, settings):
        self.settings = settings

    def language(self) -> str:
        return self.settings.get("language", "en")

    def set_language(self, lang: str) -> None:
        self.settings.set("language", lang)

    def t(self, key: str, **kwargs) -> str:
        lang = self.language()
        text = TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)
        return text.format(**kwargs)
