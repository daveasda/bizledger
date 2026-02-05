from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import Business, Membership

@login_required
def select_business(request):
    memberships = Membership.objects.select_related("business").filter(user=request.user)

    if request.method == "POST":
        business_id = request.POST.get("business_id")
        if memberships.filter(business_id=business_id).exists():
            request.session["current_business_id"] = int(business_id)
            return redirect("/")  # go to home
        # if not allowed, just reload page (simple MVP)

    return render(request, "org/select_business.html", {"memberships": memberships})
