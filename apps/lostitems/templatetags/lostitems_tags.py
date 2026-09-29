from django import template

from apps.lostitems.services import report_data

register = template.Library()


@register.inclusion_tag('lostitems/_panel.html', takes_context=True)
def lost_items_panel(context, student):
    """
    The 'Lost Items' box for the student detail page:
        {% load lostitems_tags %}  ...  {% lost_items_panel student %}
    """
    request = context.get('request')
    user = getattr(request, 'user', None)

    r = report_data(student)
    # unpaid first, newest first
    items = sorted(r['items'], key=lambda i: (i.status == 'paid', -i.date_lost.toordinal()))

    return {
        'student': student,
        'items': items,
        'total': r['total'],
        'paid': r['paid'],
        'balance': r['balance'],
        'percent': r['percent'],
        'can_manage': bool(user and (user.is_staff or user.is_superuser)),
        'is_superuser': bool(user and user.is_superuser),
        'csrf_token': context.get('csrf_token'),
    }
