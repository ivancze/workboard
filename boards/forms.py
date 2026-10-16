from django import forms
from django.db import models

from accounts.models import User

from .models import MAX_SUBTASKS, Board, Card, Subtask


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["name"]
        labels = {"name": "Board name"}


class CardPriorityForm(forms.ModelForm):
    """Priority alone, as set from the dropdown on a Card's tile."""

    class Meta:
        model = Card
        fields = ["priority"]


class SubtaskForm(forms.ModelForm):
    class Meta:
        model = Subtask
        fields = ["text"]
        labels = {"text": "Subtask"}


class SubtaskTickForm(forms.Form):
    """The state wanted, not a toggle: two ticks from the same stale page
    both mean done."""

    done = forms.BooleanField(required=False)


class BoardDescriptionForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["description"]


class BoardPetForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["pet"]


class InviteForm(forms.Form):
    email = forms.EmailField(
        label="Email address",
        help_text="The address they sign in to Google with. Nothing is sent: tell them yourself.",
    )


class DeleteBoardForm(forms.Form):
    # Not stripped: "exactly" means exactly.
    name = forms.CharField(label="Board name", strip=False)

    def __init__(self, *args, board, **kwargs):
        super().__init__(*args, **kwargs)
        self.board = board

    def clean_name(self):
        if self.cleaned_data["name"] != self.board.name:
            raise forms.ValidationError("That does not match the board name. Nothing was deleted.")
        return self.cleaned_data["name"]


class StageForm(forms.Form):
    name = forms.CharField(max_length=50, label="Stage name")


class MoveCardForm(forms.Form):
    stage = forms.ModelChoiceField(queryset=None)
    # Where a drop landed, as the id of the Card just below it (`before`) or,
    # at the bottom, just above it (`after`). Never a position: with Cards
    # hidden by a filter, or a stale page, the index on screen isn't the
    # Card's place in the Stage. Left out by the Move buttons, which send a
    # Card to the bottom.
    before = forms.IntegerField(min_value=1, required=False)
    after = forms.IntegerField(min_value=1, required=False)

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
            "priority",
            "assignee",
            "contact_persons",
            "due_date",
            "effort",
        ]
        help_texts = {
            "description": "Markdown supported.",
            "contact_persons": "People outside the board, e.g. Lando Hamilton po",
            "effort": (
                "How much work this Card represents, in a unit your team agrees on:"
                " hours, days or a score. Leave empty if Unestimated."
            ),
        }
        widgets = {
            "due_date": DateInput(),
            # Stepper arrows. The model's validators are what enforce these.
            "effort": forms.NumberInput(attrs={"min": "0", "step": "0.1"}),
        }

    def __init__(self, *args, board, **kwargs):
        super().__init__(*args, **kwargs)
        # Only this board's Members are offered, and anyone else is rejected
        # as an invalid choice rather than trusted from the POST.
        self.fields["assignee"].queryset = User.objects.filter(
            memberships__board=board
        ).order_by("display_name", "email")
        # Named like Unassigned and Unestimated, rather than Django's dashes.
        self.fields["priority"].choices = [("", "No priority"), *Card.Priority.choices]


class BaseSubtaskFormSet(forms.BaseInlineFormSet):
    """A Card's Subtasks as rows on New card and Edit: rename, remove or add.

    Saving touches only the rows that changed, and only their text, so a
    Subtask added, ticked or moved on the Card's page meanwhile isn't undone.
    Validate it under the Card's lock (lock_card): the cap is counted against
    the Subtasks the Card has by then, not those the form was opened with.
    """

    def __init__(self, data=None, *args, **kwargs):
        # A post with no rows at all, such as an Edit page opened before
        # Subtasks existed, says nothing about them: it changes none.
        prefix = kwargs.get("prefix") or self.get_default_prefix()
        if data is not None and f"{prefix}-TOTAL_FORMS" not in data:
            data = data.copy()
            data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"})
        super().__init__(data, *args, **kwargs)

    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.fields["id"].error_messages["invalid_choice"] = (
            "Someone deleted this Subtask while you were editing. Remove the row,"
            " or clear it and add it again."
        )

    def clean(self):
        super().clean()
        existing = set(self.instance.subtasks.values_list("pk", flat=True)) if self.instance.pk else set()
        kept = len(existing)
        for form in self.forms:
            removed = self.can_delete and self._should_delete_form(form)
            if form.instance.pk in existing:
                kept -= removed
            elif form.has_changed() and not removed:
                kept += 1
        if kept > MAX_SUBTASKS:
            raise forms.ValidationError(f"A Card holds at most {MAX_SUBTASKS} Subtasks.")

    def save_rows(self):
        """Write the rows that changed. New ones go to the bottom, in the
        order given. Call it under the Card's lock, after the Card is saved."""
        changed = self.save(commit=False)
        for subtask in self.deleted_objects:
            subtask.delete()
        last = Subtask.objects.filter(card=self.instance).aggregate(last=models.Max("position"))["last"]
        position = -1 if last is None else last
        for subtask in changed:
            if subtask.pk is None:
                position += 1
                subtask.position = position
                subtask.save()
            else:
                subtask.save(update_fields=["text"])


SubtaskFormSet = forms.inlineformset_factory(
    Card,
    Subtask,
    formset=BaseSubtaskFormSet,
    fields=["text"],
    labels={"text": "Subtask"},
    widgets={"text": forms.TextInput(attrs={"placeholder": "A Subtask"})},
    extra=1,
    can_delete=True,
    max_num=MAX_SUBTASKS,
)
