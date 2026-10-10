from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import DisplayNameForm


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
