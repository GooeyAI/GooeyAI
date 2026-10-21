from typing import Any

import simplejson
from django.core.validators import RegexValidator, URLValidator
from django.db import models

# Keep the raw HTML rendered downstream constrained to a safe Font Awesome
# `<i>` tag and a hex color.
validate_fa_icon = RegexValidator(
    r'^<i class="[\w\s-]+"></i>\Z',
    'Must be a single Font Awesome icon tag, e.g. <i class="fa-regular fa-tag"></i>',
)
validate_hex_color = RegexValidator(
    r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z", "Must be a hex color, e.g. #4d8af0"
)


class CustomURLField(models.URLField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 2048)
        super().__init__(*args, **kwargs)

    def clean(self, value, model_instance):
        if "://" not in value:
            value = "http://" + value

        # allow blanks - that will be validated separately (e.g. with blank=True)
        if value:
            URLValidator(schemes=["http", "https"])(value)

        return super().clean(value, model_instance)


class StrippedTextField(models.TextField):
    def clean(self, value, model_instance):
        if value:
            value = value.strip()
        return super().clean(value, model_instance)


class PostgresJSONEncoder(simplejson.JSONEncoder):
    """
    A JSONEncoder subclass that knows how to handle
    - this stupid postgres bug: https://stackoverflow.com/questions/31671634/handling-unicode-sequences-in-postgresql/31672314#31672314
    - handles NaN: https://stackoverflow.com/questions/28639953/python-json-encoder-convert-nans-to-null-instead
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.ignore_nan = True

    def encode(self, o):
        ret = super().encode(o)
        ret = ret.replace("\\u0000", "")
        return ret
