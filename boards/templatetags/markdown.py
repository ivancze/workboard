from django import template
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

register = template.Library()

# `html: False` escapes raw HTML instead of passing it through, and markdown-it
# refuses to link javascript:, vbscript:, file: and data: URLs. Together these
# make the output safe to mark as such without a separate sanitiser.
_renderer = MarkdownIt("commonmark", {"html": False})


@register.filter
def markdown(text):
    return mark_safe(_renderer.render(text))
