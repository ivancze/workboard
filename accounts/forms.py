from django import forms

from .models import User


class DisplayNameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["display_name"]
        labels = {"display_name": "Display name"}
