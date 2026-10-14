"""Reusable function-based CRUD builder.

Every monitoring entity exposes the same four JSON endpoints used elsewhere in
the project (list, get, save, delete) plus a page view.  This module builds
those views so the entity modules stay small and consistent.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.html import escape
from django.views.decorators.http import require_POST

PER_PAGE = 10


def _scoped(user, model):
    """Return the queryset of records the user is allowed to see.

    Superusers see everything; regular users only their own records.
    """
    if user.is_superuser:
        return model.objects.all()
    return model.objects.filter(user=user)


def _filter(qs, search_fields, query):
    if not query or not search_fields:
        return qs
    condition = Q()
    for field in search_fields:
        condition |= Q(**{f'{field}__icontains': query})
    return qs.filter(condition)


def _format_cell(value, column):
    if value is None or value == '':
        return '<span class="text-muted">—</span>'

    kind = column.get('type')
    if kind in ('date', 'datetime') and isinstance(value, (date, datetime)):
        fmt = '%b %d, %Y' if kind == 'date' else '%b %d, %Y %H:%M'
        return escape(value.strftime(fmt))
    if kind == 'money':
        try:
            return escape(f'₱{Decimal(value):,.2f}')
        except (InvalidOperation, TypeError):
            return escape(str(value))
    return escape(str(value))


def _badge(value, column):
    mapping = column.get('badge')
    if not mapping:
        return None
    return mapping.get(str(value))


def _build_rows(objects, columns):
    rows = []
    for obj in objects:
        cells = []
        for column in columns:
            value = getattr(obj, column['field'], '')
            if callable(value):
                value = value()

            badge_value = value
            raw_field = column.get('raw_field')
            if raw_field:
                badge_value = getattr(obj, raw_field, value)

            cells.append({
                'html': _format_cell(value, column),
                'badge': _badge(badge_value, column),
            })
        rows.append({'id': obj.pk, 'cells': cells})
    return rows


def _serialize(value):
    if hasattr(value, 'pk'):
        return str(value.pk)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if value is None:
        return ''
    return str(value)


def describe_fields(form):
    """Describe a bound/unbound form's fields for generic template rendering."""
    fields = []
    for name, field in form.fields.items():
        widget = field.widget
        wtype = widget.__class__.__name__

        if wtype in ('Select', 'SelectMultiple'):
            kind = 'select'
        elif wtype == 'Textarea':
            kind = 'textarea'
        elif wtype == 'CheckboxInput':
            kind = 'checkbox'
        elif wtype in ('ClearableFileInput', 'FileInput'):
            kind = 'file'
        elif wtype == 'NumberInput':
            kind = 'number'
        elif wtype == 'DateTimeInput':
            kind = 'datetime-local'
        elif wtype == 'DateInput':
            kind = 'date'
        elif wtype == 'EmailInput':
            kind = 'email'
        else:
            kind = 'text'

        fields.append({
            'name': name,
            'label': field.label or name.replace('_', ' ').title(),
            'kind': kind,
            'required': field.required,
            'choices': list(field.choices) if kind == 'select' and field.choices else [],
            'help': str(field.help_text or ''),
        })
    return fields


def make_crud(*, model, form_class, columns, search_fields=(), order_by=None,
              title, pretitle='Overview', entity='Record', add_label='Add Record',
              search_placeholder='Search...'):
    """Build the page + AJAX views for a single model.

    Returns a dict of view callables keyed by ``page``, ``list_ajax``,
    ``get_ajax``, ``save_ajax`` and ``delete_ajax``.
    """
    if order_by is None:
        order_by = model._meta.ordering or ['-pk']

    form_field_names = list(form_class().fields.keys())

    def _base_queryset(request, query=''):
        qs = _scoped(request.user, model)
        qs = _filter(qs, search_fields, query)
        return qs.order_by(*order_by)

    def _row_data(objects):
        return {
            str(obj.pk): {name: _serialize(getattr(obj, name, '')) for name in form_field_names}
            for obj in objects
        }

    @login_required(login_url='login')
    def page(request):
        query = request.GET.get('q', '').strip()
        queryset = _base_queryset(request, query)

        paginator = Paginator(queryset, PER_PAGE)
        page_obj = paginator.get_page(request.GET.get('page', 1))

        context = {
            'page_title': title,
            'page_pretitle': pretitle,
            'add_label': add_label,
            'entity': entity,
            'columns': columns,
            'form_fields': describe_fields(form_class(user=request.user)),
            'rows': _build_rows(page_obj.object_list, columns),
            'rows_json': _row_data(page_obj.object_list),
            'page_obj': page_obj,
            'query': query,
            'search_placeholder': search_placeholder,
            'colspan': len(columns) + 2,
            'search_fields': search_fields,
        }
        return render(request, 'ofw/crud.html', context)

    @login_required(login_url='login')
    def list_ajax(request):
        query = request.GET.get('q', '').strip()
        queryset = _base_queryset(request, query)

        paginator = Paginator(queryset, PER_PAGE)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        return JsonResponse({
            'data': _build_rows(page_obj.object_list, columns),
            'has_next': page_obj.has_next(),
            'has_prev': page_obj.has_previous(),
            'page': page_obj.number,
            'pages': paginator.num_pages,
            'total': paginator.count,
        })

    @login_required(login_url='login')
    def get_ajax(request, pk):
        obj = get_object_or_404(_scoped(request.user, model), pk=pk)
        return JsonResponse({
            name: _serialize(getattr(obj, name, '')) for name in form_field_names
        })

    @login_required(login_url='login')
    @require_POST
    def save_ajax(request):
        record_id = request.POST.get('id')
        if record_id:
            obj = get_object_or_404(_scoped(request.user, model), pk=record_id)
            is_update = True
        else:
            obj = model()
            is_update = False

        form = form_class(request.POST, request.FILES, instance=obj, user=request.user)
        if not form.is_valid():
            errors = [msg for errs in form.errors.values() for msg in errs]
            return JsonResponse({'error': ' '.join(errors)}, status=400)

        obj = form.save(commit=False)
        if not obj.pk and hasattr(obj, 'user'):
            obj.user = request.user
        obj.save()

        messages.success(
            request,
            f'{entity} "{obj}" has been {"updated" if is_update else "saved"} successfully.',
        )
        return JsonResponse({'status': 'success', 'id': obj.pk})

    @login_required(login_url='login')
    @require_POST
    def delete_ajax(request, pk):
        obj = get_object_or_404(_scoped(request.user, model), pk=pk)
        label = str(obj)
        obj.delete()
        messages.success(request, f'{entity} "{label}" has been deleted successfully.')
        return JsonResponse({'status': 'deleted'})

    return {
        'page': page,
        'list_ajax': list_ajax,
        'get_ajax': get_ajax,
        'save_ajax': save_ajax,
        'delete_ajax': delete_ajax,
    }
