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
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_POST

from apps.users.agencies import agency_for_user

from .models import EmergencyContact, MonitoringReport, OFWProfile

PER_PAGE = 10


def _scoped(user, model):
    """Return the queryset of records the user is allowed to see.

    Superusers and legacy staff without an agency see everything.  Agency
    staff only see records belonging to their own agency.  OFW accounts only
    see their own records.
    """
    if user.is_superuser:
        return model.objects.all()

    agency = agency_for_user(user)
    if user.is_staff:
        if agency is None:
            # Legacy global staff account.
            return model.objects.all()
        if model is OFWProfile:
            return model.objects.filter(agency_org=agency)
        if model is EmergencyContact:
            return model.objects.filter(
                Q(user__isnull=True) |
                Q(user__ofw_profiles__agency_org=agency)
            ).distinct()
        if model is MonitoringReport:
            return model.objects.filter(agency=agency)
        if hasattr(model, 'ofw'):
            return model.objects.filter(ofw__agency_org=agency)
        return model.objects.none()

    return model.objects.filter(user=user)


def _filter(qs, search_fields, query):
    if not query or not search_fields:
        return qs
    condition = Q()
    for field in search_fields:
        condition |= Q(**{f'{field}__icontains': query})
    return qs.filter(condition)


def csv_list(value):
    """Turn a comma-separated query value into a clean list (for ``__in`` filters)."""
    return [item for item in value.split(',') if item]


def _apply_filters(qs, filters, params):
    """Apply configured query-string filters to a queryset.

    ``filters`` maps a query parameter name to a ``(lookup, transform)`` tuple,
    e.g. ``{'status': ('status__in', csv_list)}``.  Empty values are ignored.
    """
    for key, (lookup, transform) in (filters or {}).items():
        raw = params.get(key)
        if raw in (None, ''):
            continue
        try:
            value = transform(raw)
        except (TypeError, ValueError):
            continue
        qs = qs.filter(**{lookup: value})
    return qs


def _format_cell(value, column):
    kind = column.get('type')

    if kind == 'image':
        url = ''
        if value:
            try:
                url = value.url
            except (ValueError, AttributeError):
                url = ''
        if url:
            return (
                f'<img src="{escape(url)}" alt="Profile picture" '
                'class="avatar avatar-sm rounded-circle" '
                'style="object-fit: cover;" loading="lazy">'
            )
        return (
            '<span class="avatar avatar-sm rounded-circle bg-secondary-lt '
            'text-secondary"><i class="fas fa-user"></i></span>'
        )

    if value is None or value == '':
        return '<span class="text-muted">—</span>'

    if kind in ('date', 'datetime') and isinstance(value, (date, datetime)):
        fmt = '%b %d, %Y' if kind == 'date' else '%b %d, %Y %H:%M'
        return escape(value.strftime(fmt))
    if kind == 'money':
        try:
            return escape(f'₱{Decimal(value):,.2f}')
        except (InvalidOperation, TypeError):
            return escape(str(value))

    text = str(value)
    limit = column.get('truncate')
    if limit and len(text) > limit:
        return f'<span title="{escape(text)}">{escape(text[:limit].rstrip())}…</span>'
    return escape(text)


def _badge(value, column):
    mapping = column.get('badge')
    if not mapping:
        return None
    return mapping.get(str(value))


def _build_rows(objects, columns, row_actions=None):
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
                'url': reverse(column['url_name'], args=[obj.pk]) if column.get('url_name') else None,
            })

        actions = row_actions(obj) if row_actions else []
        rows.append({'id': obj.pk, 'cells': cells, 'actions': actions})
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
              search_placeholder='Search...', detail_url_name=None, filters=None,
              row_actions=None, on_save=None, on_delete=None):
    """Build the page + AJAX views for a single model.

    Returns a dict of view callables keyed by ``page``, ``list_ajax``,
    ``get_ajax``, ``save_ajax`` and ``delete_ajax``.

    ``row_actions`` is an optional callable ``fn(obj) -> list[dict]`` that adds
    extra action buttons to every row (e.g. a ``tel:`` call link or an external
    website link).  Each action supports ``title``, ``icon``, ``icon_class``,
    ``href`` and ``target``.

    ``on_save`` receives ``(obj, created, actor, previous)`` after a successful
    save, where ``previous`` holds the field values before an update.  This is
    used to raise notifications only when something meaningful changed.
    ``on_delete`` receives ``(obj, actor)`` before the record is removed.
    """
    if order_by is None:
        order_by = model._meta.ordering or ['-pk']

    form_field_names = list(form_class().fields.keys())

    def _base_queryset(request, query=''):
        qs = _scoped(request.user, model)
        qs = _apply_filters(qs, filters, request.GET)
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

        params = request.GET.copy()
        params.pop('page', None)
        filter_items = [
            (key, request.GET.get(key))
            for key in (filters or {})
            if request.GET.get(key)
        ]

        context = {
            'page_title': title,
            'page_pretitle': pretitle,
            'add_label': add_label,
            'entity': entity,
            'columns': columns,
            'form_fields': describe_fields(form_class(user=request.user)),
            'rows': _build_rows(page_obj.object_list, columns, row_actions),
            'rows_json': _row_data(page_obj.object_list),
            'page_obj': page_obj,
            'query': query,
            'querystring': params.urlencode(),
            'filter_items': filter_items,
            'search_placeholder': search_placeholder,
            'colspan': len(columns) + 2,
            'search_fields': search_fields,
            'detail_url_name': detail_url_name,
        }
        return render(request, 'ofw/crud.html', context)

    @login_required(login_url='login')
    def list_ajax(request):
        query = request.GET.get('q', '').strip()
        queryset = _base_queryset(request, query)

        paginator = Paginator(queryset, PER_PAGE)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        return JsonResponse({
            'data': _build_rows(page_obj.object_list, columns, row_actions),
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
        previous = {}
        if record_id:
            obj = get_object_or_404(_scoped(request.user, model), pk=record_id)
            is_update = True
            previous = {
                field.name: getattr(obj, field.name, None)
                for field in model._meta.fields
            }
        else:
            obj = model()
            is_update = False

        form = form_class(request.POST, request.FILES, instance=obj, user=request.user)
        if not form.is_valid():
            errors = [msg for errs in form.errors.values() for msg in errs]
            return JsonResponse({'error': ' '.join(errors)}, status=400)

        obj = form.save(commit=False)
        agency = agency_for_user(request.user)
        if agency is not None:
            if hasattr(obj, 'agency_org'):
                obj.agency_org = agency
            if model is MonitoringReport:
                obj.agency = agency
        if not obj.pk and hasattr(obj, 'user'):
            # An agency officer adding a paper profile should not turn that
            # profile into their own OFW portal account.  Directory contacts
            # are shared entries, so they are not owned by the officer either.
            if not (
                agency is not None
                and model in (OFWProfile, EmergencyContact)
            ):
                obj.user = request.user
        obj.save()

        if on_save:
            on_save(obj, not is_update, request.user, previous)

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
        if on_delete:
            on_delete(obj, request.user)
        obj.delete()
        messages.success(request, f'{entity} "{label}" has been deleted successfully.')
        return JsonResponse({'status': 'deleted'})

    @login_required(login_url='login')
    @require_POST
    def delete_all_ajax(request):
        if not (request.user.is_superuser or request.user.is_staff):
            return JsonResponse({'error': 'Not allowed.'}, status=403)

        queryset = _scoped(request.user, model)
        count = queryset.count()
        if count == 0:
            messages.info(request, f'No {entity.lower()} records to delete.')
            return JsonResponse({'status': 'deleted_all', 'count': 0})

        # Call on_delete for each object if provided (for side effects like files)
        if on_delete:
            for obj in queryset:
                try:
                    on_delete(obj, request.user)
                except Exception:
                    # Don't block bulk deletion on callback errors
                    pass

        queryset.delete()
        messages.success(request, f'All {entity.lower()} records ({count}) have been deleted successfully.')
        return JsonResponse({'status': 'deleted_all', 'count': count})

    return {
        'page': page,
        'list_ajax': list_ajax,
        'get_ajax': get_ajax,
        'save_ajax': save_ajax,
        'delete_ajax': delete_ajax,
        'delete_all_ajax': delete_all_ajax,
    }
