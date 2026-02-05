from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from .models import Invoice

@login_required
def invoice_list(request):
    business_id = request.session.get("current_business_id")
    mode = request.session.get("current_mode", "BUSINESS")
    invoices = Invoice.objects.filter(business_id=business_id, mode=mode).order_by("-date", "-id")
    return render(request, "billing/invoice_list.html", {"invoices": invoices})

@login_required
def invoice_detail(request, invoice_id: int):
    business_id = request.session.get("current_business_id")
    mode = request.session.get("current_mode", "BUSINESS")
    inv = get_object_or_404(Invoice, id=invoice_id, business_id=business_id, mode=mode)
    return render(request, "billing/invoice_detail.html", {"inv": inv})
