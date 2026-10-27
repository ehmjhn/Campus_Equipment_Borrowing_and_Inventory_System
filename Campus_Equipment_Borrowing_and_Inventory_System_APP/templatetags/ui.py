"""Small presentation helpers shared by every template."""

from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name, css_class="icon"):
    """Render an inline SVG reference from the sprite in base.html."""
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<use href="#i-{}"></use></svg>',
        css_class,
        name,
    )
