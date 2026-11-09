"""Reusable function-based CRUD builder.

Every monitoring entity exposes the same four JSON endpoints used elsewhere in
the project (list, get, save, delete) plus a page view.  This module builds
those views so the entity modules stay small and consistent.
"""

import csv
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from apps.users.agencies import agency_for_user, has_agency_assignment, is_global_staff

from .models import AuditLog, EmergencyContact, MonitoringReport, OFWProfile

PER_PAGE = 10


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _write_audit(request, action, model, *, obj=None, changes=None, object_id='', object_repr=''):
    """Record a management action without blocking the main request."""
    try:
        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            model_name=model._meta.verbose_name.title(),
            object_id=str(obj.pk) if obj is not None else object_id,
            object_repr=(str(obj) if obj is not None else object_repr)[:255],
            changes=json.dumps(changes or {}, default=str),
            ip_address=_client_ip(request),
        )
    except Exception:
        # Auditing must never break the action the user requested.
        pass


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
            # A staff account with an agency row whose agency is disabled must
            # see nothing, not every agency's records.
            if has_agency_assignment(user):
                return model.objects.none()
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
        if isinstance(value, Q):
            qs = qs.filter(value)
        else:
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

            meta_parts = []
            for meta_field in column.get('meta_fields', []):
                meta_value = getattr(obj, meta_field, '')
                if callable(meta_value):
                    meta_value = meta_value()
                if meta_value not in (None, ''):
                    meta_parts.append(escape(str(meta_value)))

            cells.append({
                'html': _format_cell(value, column),
                'badge': _badge(badge_value, column),
                'meta': ' · '.join(meta_parts),
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


def _excel_value(value):
    """Convert a model value to something openpyxl can safely store."""
    if value is None:
        return ''
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, 'pk'):
        return str(value.pk)
    return str(value)


def _xlsx_response(queryset, field_names, field_labels, entity):
    """Stream an .xlsx workbook for the current (filtered) queryset."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = (entity or 'Records')[:31]

    sheet.append([field_labels.get(name, name.replace('_', ' ').title()) for name in field_names])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1F3A5F')
        cell.alignment = Alignment(vertical='center')

    for obj in queryset.iterator():
        sheet.append([_excel_value(getattr(obj, name, '')) for name in field_names])

    sheet.freeze_panes = 'A2'
    for index, _name in enumerate(field_names, start=1):
        longest = max(
            (len(str(sheet.cell(row=row, column=index).value or ''))
             for row in range(1, sheet.max_row + 1)),
            default=0,
        )
        sheet.column_dimensions[get_column_letter(index)].width = min(max(12, longest + 2), 50)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'{entity.lower().replace(" ", "_")}_export.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response


def describe_fields(form):
    """Describe a bound/unbound form's fields for generic template rendering."""
    fields = []
    datalists = getattr(form, 'datalists', {})
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
            'placeholder': widget.attrs.get('placeholder', ''),
            'datalist_id': widget.attrs.get('list', ''),
            'datalist': datalists.get(name, []),
            'cities_url': _reversed_url(widget.attrs.get('data-cities-url', '')),
            'public_types': widget.attrs.get('data-public-types', ''),
        })
    return fields


def _reversed_url(view_name):
    """Resolve a lazily declared URL name without crashing the whole form."""
    if not view_name:
        return ''
    try:
        return reverse(view_name)
    except NoReverseMatch:
        return ''


def make_crud(*, model, form_class, columns, search_fields=(), order_by=None,
              title, pretitle='Overview', entity='Record', add_label='Add Record',
              search_placeholder='Search...', detail_url_name=None, filters=None,
              row_actions=None, on_save=None, on_delete=None, page_help=None,
              allow_delete_all=True):
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
            'page_help': page_help or [],
            'allow_delete_all': allow_delete_all,
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
        if not (request.user.is_superuser or request.user.is_staff):
            if model is not OFWProfile:
                return JsonResponse(
                    {'error': 'Management accounts only.'}, status=403
                )
            if not request.user.ofw_profiles.exists() and request.POST.get('id'):
                return JsonResponse({'error': 'Profile not found.'}, status=404)

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
            if (
                model is OFWProfile
                and not (request.user.is_superuser or request.user.is_staff)
                and request.user.ofw_profiles.exists()
            ):
                return JsonResponse(
                    {'error': 'Your account already has an OFW profile.'},
                    status=400,
                )
            obj = model()
            is_update = False

        form = form_class(request.POST, request.FILES, instance=obj, user=request.user)
        if not form.is_valid():
            errors = [msg for errs in form.errors.values() for msg in errs]
            return JsonResponse({'error': ' '.join(errors)}, status=400)

        obj = form.save(commit=False)
        agency = agency_for_user(request.user)
        if not (request.user.is_superuser or request.user.is_staff):
            # Non-staff accounts may only save their own profile; never let the
            # generic endpoint attach it to an agency or another user.
            obj.user = request.user
            if hasattr(obj, 'agency_org'):
                obj.agency_org = None
        elif agency is not None:
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

        if is_update:
            changed = {}
            for name in form.changed_data:
                before = _serialize(previous.get(name, ''))
                after = _serialize(getattr(obj, name, ''))
                if before != after:
                    changed[name] = {'from': before, 'to': after}
            _write_audit(request, AuditLog.Action.UPDATE, model, obj=obj, changes=changed)
        else:
            created = {
                name: _serialize(getattr(obj, name, ''))
                for name in form_field_names
                if name not in ('profile_picture', 'attachment')
            }
            _write_audit(request, AuditLog.Action.CREATE, model, obj=obj, changes=created)

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
        if not (request.user.is_superuser or request.user.is_staff):
            return JsonResponse({'error': 'Management accounts only.'}, status=403)
        obj = get_object_or_404(_scoped(request.user, model), pk=pk)
        label = str(obj)
        _write_audit(request, AuditLog.Action.DELETE, model, obj=obj)
        if on_delete:
            on_delete(obj, request.user)
        obj.delete()
        messages.success(request, f'{entity} "{label}" has been deleted successfully.')
        return JsonResponse({'status': 'deleted'})

    @login_required(login_url='login')
    @require_POST
    def delete_all_ajax(request):
        if not request.user.is_superuser:
            return JsonResponse(
                {'error': 'Only administrators can delete all records.'},
                status=403,
            )

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
        _write_audit(
            request,
            AuditLog.Action.DELETE_ALL,
            model,
            object_repr=f'{count} {entity.lower()} records',
            changes={'count': count},
        )
        messages.success(request, f'All {entity.lower()} records ({count}) have been deleted successfully.')
        return JsonResponse({'status': 'deleted_all', 'count': count})

    @login_required(login_url='login')
    def export_ajax(request):
        """Export the current filtered queryset as Excel.

        CSV remains available for compatibility via ``?format=csv``.
        """
        query = request.GET.get('q', '').strip()
        queryset = _base_queryset(request, query)

        # Build header from form field names, excluding relational/file fields
        # that don't serialize well to a spreadsheet.
        field_names = [
            name for name in form_field_names
            if name not in ('profile_picture', 'attachment', 'user')
        ]

        export_format = request.GET.get('format', 'xlsx').lower()
        if export_format == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{entity.lower()}_export.csv"'

            writer = csv.writer(response)
            writer.writerow(field_names)

            for obj in queryset:
                row = []
                for name in field_names:
                    value = getattr(obj, name, '')
                    if callable(value):
                        value = value()
                    if isinstance(value, (date, datetime)):
                        value = value.isoformat()
                    elif hasattr(value, 'pk'):
                        value = str(value.pk)
                    elif value is None:
                        value = ''
                    row.append(str(value))
                writer.writerow(row)
            export_label = 'CSV'
        else:
            form = form_class()
            field_labels = {
                name: (form.fields[name].label or name.replace('_', ' ').title())
                for name in field_names
            }
            response = _xlsx_response(queryset, field_names, field_labels, entity)
            export_label = 'Excel'

        export_count = queryset.count()
        _write_audit(
            request,
            AuditLog.Action.EXPORT,
            model,
            object_repr=f'{export_count} {entity.lower()} records',
            changes={'count': export_count, 'format': export_label},
        )
        messages.success(
            request,
            f'Exported {export_count} '
            f'{entity.lower() if entity.endswith("s") else entity + "s"} '
            f'records to {export_label}.',
        )
        return response

    return {
        'page': page,
        'list_ajax': list_ajax,
        'get_ajax': get_ajax,
        'save_ajax': save_ajax,
        'delete_ajax': delete_ajax,
        'delete_all_ajax': delete_all_ajax,
        'export_ajax': export_ajax,
    }
