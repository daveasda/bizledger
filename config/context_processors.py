from django.utils import timezone

from config.financial_year import (
    financial_year_bounds,
    financial_year_label,
    financial_year_start,
)


def financial_year(request):
    """Expose current FY (in TIME_ZONE) to all templates."""
    today = timezone.localdate()
    start = financial_year_start(today)
    _, end = financial_year_bounds(today)
    return {
        "fy_today": today,
        "fy_start": start,
        "fy_end": end,
        "fy_label": financial_year_label(today),
    }
