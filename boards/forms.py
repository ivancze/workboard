from django import forms

from accounts.models import User

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


class MoveCardForm(forms.Form):
    stage = forms.ModelChoiceField(queryset=None)

    def __init__(self, *args, board, **kwargs):
        super().__init__(*args, **kwargs)
        # A Stage of another board is simply not a valid choice.
        self.fields["stage"].queryset = board.stages.all()


class DateInput(forms.DateInput):
    """The browser's date picker. It submits ISO dates, so render them too."""

    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class MemberChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return user.name


class CardForm(forms.ModelForm):
    assignee = MemberChoiceField(
        queryset=User.objects.none(), required=False, empty_label="Unassigned"
    )

    class Meta:
        model = Card
        fields = [
            "title",
            "description",
            "assignee",
            "contact_persons",
            "due_date",
            "effort",
        ]
        help_texts = {
            "description": "Markdown. HTML is shown as plain text.",
            "contact_persons": "People outside the board, e.g. Dave, Priya from Acme.",
            "effort": "In steps of 0.5. Leave empty if Unestimated.",
        }
        widgets = {
            "due_date": DateInput(),
            # Stepper arrows. The model's validators are what enforce these.
            "effort": forms.NumberInput(attrs={"min": "0", "step": "0.5"}),
        }

    def __init__(self, *args, board, **kwargs):
        super().__init__(*args, **kwargs)
        # Only this board's Members are offered, and anyone else is rejected
        # as an invalid choice rather than trusted from the POST.
        self.fields["assignee"].queryset = User.objects.filter(
            memberships__board=board
        ).order_by("display_name", "email")
