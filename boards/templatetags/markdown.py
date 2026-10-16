from django import template
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

register = template.Library()

# `html: False` escapes raw HTML instead of passing it through, and markdown-it
# refuses to link javascript:, vbscript:, file: and data: URLs. Together these
# make the output safe to mark as such without a separate sanitiser.
# `breaks: True` keeps a single newline as a line break, as GitHub comments do;
# strict CommonMark would join the lines into one.
_renderer = MarkdownIt("commonmark", {"html": False, "breaks": True})


@register.filter
def markdown(text):
    return mark_safe(_renderer.render(text))
