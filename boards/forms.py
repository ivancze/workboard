from django import forms

from .models import Board, Card


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["name"]
        labels = {"name": "Board name"}


class NewCardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ["title"]
        labels = {"title": "Card title"}


class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ["title", "description"]
        help_texts = {"description": "Markdown. HTML is shown as plain text."}
