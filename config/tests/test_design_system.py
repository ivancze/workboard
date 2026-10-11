import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from boards.models import Board, Card

STYLESHEET = '<link rel="stylesheet" href="/static/css/app.css">'
TOKENS = Path(settings.BASE_DIR, "assets", "app.css")


def a_user(email="ada@example.com"):
    return User.objects.create_user(email=email, display_name=email.split("@")[0])


class EveryPageUsesTheSystemTests(TestCase):
    """Nothing a person can reach should render with browser default styling."""

    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.card = Card.objects.create_at_end(
            stage=self.board.stages.first(), title="Buy milk", creator=self.ada
        )

    def signed_in_pages(self):
        return [
            reverse("home"),
            reverse("board_detail", args=[self.board.pk]),
            reverse("card_detail", args=[self.board.pk, self.card.pk]),
            reverse("profile"),
            reverse("account_logout"),
        ]

    def test_signed_out_pages(self):
        # The Google page is where LOGIN_URL sends a signed-out visitor.
        for url in [reverse("home"), reverse("google_login"), reverse("account_login")]:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), STYLESHEET)

    def test_the_provider_list_is_styled(self):
        """allauth's own markup for /accounts/login/, which is reachable from
        the login-cancelled page, rather than a bare list of links."""
        response = self.client.get(reverse("account_login"))

        self.assertRegex(
            response.content.decode(), r'<a href="/accounts/google/login/[^"]*" class="[^"]*bg-accent'
        )

    def test_signed_in_pages(self):
        self.client.force_login(self.ada)
        for url in self.signed_in_pages():
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), STYLESHEET)

    def test_the_stored_theme_is_applied_before_the_stylesheet_loads(self):
        """Applying it any later lets the page paint once in the wrong theme."""
        content = self.client.get(reverse("home")).content.decode()

        head = content[: content.index("</head>")]
        self.assertIn('localStorage.getItem("theme")', head)
        self.assertLess(
            head.index('localStorage.getItem("theme")'), head.index(STYLESHEET)
        )

    def test_every_page_offers_the_theme_toggle(self):
        self.client.force_login(self.ada)
        for url in self.signed_in_pages():
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), "data-theme-toggle")

    def test_form_controls_are_styled(self):
        """Django renders the <input> itself, so this proves the widget
        templates are overridden rather than left to browser defaults."""
        self.client.force_login(self.ada)

        response = self.client.get(
            reverse("card_detail", args=[self.board.pk, self.card.pk])
        )

        content = response.content.decode()
        self.assertRegex(content, r'<input[^>]*class="[^"]*border-control')
        self.assertRegex(content, r'<textarea[^>]*class="[^"]*border-control')
        self.assertRegex(content, r'<select[^>]*class="[^"]*border-control')
        self.assertRegex(content, r'<input type="date"[^>]*class="[^"]*border-control')


# `p-[13px]` and `[&>p]:…` use brackets; v4 also has `p-(--gap)`.
ARBITRARY = re.compile(r"\[|-\(")


class NoArbitraryValuesTests(TestCase):
    """A value missing from the scale belongs in @theme as a token, so
    consistency is enforced rather than hoped for."""

    def test_templates_use_only_the_scale(self):
        offenders = []
        for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
            # Tags and variables go first, so quotes inside an {% if %} in a
            # class attribute cannot end the attribute early.
            text = re.sub(r"{%.*?%}|{{.*?}}", " ", path.read_text())
            for match in re.finditer(r"""class=(["'])(.*?)\1""", text, re.S):
                offenders += [
                    f"{path.name}: {cls}"
                    for cls in match.group(2).split()
                    if ARBITRARY.search(cls)
                ]

        self.assertEqual(offenders, [])


def tokens():
    """{name: (light, dark)} for every light-dark() colour token."""
    pattern = r"--color-([\w-]+):\s*light-dark\((#[0-9a-f]{6}),\s*(#[0-9a-f]{6})\)"
    return {
        name: (light, dark)
        for name, light, dark in re.findall(pattern, TOKENS.read_text(), re.I)
    }


def luminance(hex_colour):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    high, low = sorted([luminance(a), luminance(b)], reverse=True)
    return (high + 0.05) / (low + 0.05)


BACKGROUNDS = ["canvas", "surface", "sunken"]
# 4.5:1 for text.
TEXT_PAIRS = [
    (fg, bg) for fg in ["text", "text-muted", "accent", "danger"] for bg in BACKGROUNDS
] + [("on-accent", "accent"), ("on-accent", "accent-hover")]
# 3:1 for the parts of a control that identify it, and for the focus ring.
NON_TEXT_PAIRS = [(fg, bg) for fg in ["control", "focus"] for bg in BACKGROUNDS]


class ContrastTests(TestCase):
    """WCAG AA, checked against the tokens themselves so every component
    built from them inherits the guarantee, in both themes."""

    def test_the_tokens_were_found(self):
        self.assertTrue(
            {"canvas", "surface", "sunken", "text", "accent", "focus"} <= set(tokens())
        )

    def check(self, pairs, minimum):
        found = tokens()
        for theme, index in [("light", 0), ("dark", 1)]:
            for fg, bg in pairs:
                with self.subTest(theme=theme, fg=fg, bg=bg):
                    ratio = contrast(found[fg][index], found[bg][index])
                    self.assertGreaterEqual(round(ratio, 2), minimum)

    def test_text_meets_aa(self):
        self.check(TEXT_PAIRS, 4.5)

    def test_controls_and_focus_meet_aa(self):
        self.check(NON_TEXT_PAIRS, 3)
