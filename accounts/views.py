from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import DisplayNameForm


def home(request):
    """The landing page: a sign-in prompt, or a greeting.

    Boards arrive here in a later ticket; for now this is only enough to prove
    who you are.
    """
    return render(request, "accounts/home.html")


@login_required
def profile(request):
    if request.method == "POST":
        form = DisplayNameForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect("home")
    else:
        form = DisplayNameForm(instance=request.user)

    return render(request, "accounts/profile.html", {"form": form})
