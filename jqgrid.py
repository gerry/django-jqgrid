# Copyright (c) 2009, Gerry Eisenhaur
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    1. Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#
#    2. Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#
#    3. Neither the name of the project nor the names of its contributors may
#       be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
from functools import reduce

import operator
from django.core.serializers import json
from django.db import models
from django.db.models.fields.related import RelatedField
from django.core.exceptions import FieldError, ImproperlyConfigured, FieldDoesNotExist
from django.core.paginator import Paginator, InvalidPage
from django.utils.encoding import smart_str


def json_encode(data):
    encoder = json.DjangoJSONEncoder()
    return encoder.encode(data)


class JqGrid(object):
    queryset = None
    model = None
    fields = []
    allow_empty = True
    extra_config = {}

    pager_id = '#pager'
    url = None
    caption = None
    colmodel_overrides = {}

    def get_queryset(self, request):
        if hasattr(self, 'queryset') and self.queryset is not None:
            queryset = self.queryset._clone()
        elif hasattr(self, 'model') and self.model is not None:
            queryset = self.model.objects.all()  # formerly: values(*self.get_field_names())
        else:
            raise ImproperlyConfigured("No queryset or model defined.")
        self.queryset = queryset
        return self.queryset

    def get_model(self):
        if hasattr(self, 'model') and self.model is not None:
            model = self.model
        elif hasattr(self, 'queryset') and self.queryset is not None:
            model = self.queryset.model
            self.model = model
        else:
            raise ImproperlyConfigured("No queryset or model defined.")
        return model

    def get_items(self, request):
        items = self.get_queryset(request)
        items = self.filter_items(request, items)
        items = self.sort_items(request, items)
        paginator, page, items = self.paginate_items(request, items)
        return paginator, page, items

    def get_filters(self, request):
        _search = request.GET.get('_search')
        filters = None

        # multiple field search
        _filters = request.GET.get('filters', '')
        if _filters:
            try:
                filters = json.json.loads(_filters)
            except ValueError:
                return None

        else:
            field = request.GET.get('searchField')
            op = request.GET.get('searchOper')
            data = request.GET.get('searchString')

            # single field search
            if all([field, op, data]):
                filters = {
                    'groupOp': 'AND',
                    'rules': [{'op': op, 'field': field, 'data': data}]
                }

        # toolbar search - this may work in addition to field searches
        field_names = [f.name for f in self.get_model()._meta.local_fields]
        if not filters:
            filters = {
                'groupOp': 'AND',
                'rules': []
            }
        for param in request.GET:
            if param in field_names:
                filters['rules'] += [{'op': 'cn', 'field': param, 'data': request.GET[param]}]

        return filters

    def filter_items(self, request, items):
        # TODO: Add option to use case insensitive filters
        # TODO: Add more support for RelatedFields (searching and displaying)
        # FIXME: Validate data types are correct for field being searched.
        filter_map = {
            # jqgrid op: (django_lookup, use_exclude)
            'ne': ('%(field)s__exact', True),
            'bn': ('%(field)s__startswith', True),
            'en': ('%(field)s__endswith', True),
            'nc': ('%(field)s__contains', True),
            'ni': ('%(field)s__in', True),
            'in': ('%(field)s__in', False),
            'eq': ('%(field)s__exact', False),
            'bw': ('%(field)s__startswith', False),
            'gt': ('%(field)s__gt', False),
            'ge': ('%(field)s__gte', False),
            'lt': ('%(field)s__lt', False),
            'le': ('%(field)s__lte', False),
            'ew': ('%(field)s__endswith', False),
            'cn': ('%(field)s__contains', False)
        }
        if self.get_config(False)['ignoreCase']:
            filter_map.update({'ne': ('%(field)s__iexact', True),
                               'eq': ('%(field)s__iexact', False),
                               'bn': ('%(field)s__istartswith', True),
                               'bw': ('%(field)s__istartswith', False),
                               'en': ('%(field)s__iendswith', True),
                               'ew': ('%(field)s__iendswith', False),
                               'nc': ('%(field)s__icontains', True),
                               'cn': ('%(field)s__icontains', False)
                               }
                              )
        _filters = self.get_filters(request)
        if not _filters or not _filters['rules']:
            return items

        q_filters = []
        for rule in _filters['rules']:
            op, field, data = rule['op'], rule['field'], rule['data']
            # FIXME: Restrict what lookups performed against RelatedFields
            field_class = self.get_model()._meta.get_field(field)
            if isinstance(field_class, RelatedField):
                op = 'eq'
            filter_fmt, exclude = filter_map[op]
            filter_str = smart_str(filter_fmt % {'field': field})
            if filter_fmt.endswith('__in'):
                filter_kwargs = {filter_str: data.split(',')}
            else:
                filter_kwargs = {filter_str: smart_str(data)}

            if exclude:
                q_filters.append(~models.Q(**filter_kwargs))
            else:
                q_filters.append(models.Q(**filter_kwargs))

        if _filters['groupOp'].upper() == 'OR':
            filters = reduce(operator.ior, q_filters)
        else:
            filters = reduce(operator.iand, q_filters)
        return items.filter(filters)

    @staticmethod
    def sort_items(request, items):
        sidx = request.GET.get('sidx')
        if sidx is not None:
            order_by_list = []
            sord = request.GET.get('sord')
            sidx_list = map(lambda x: x.strip(), sidx.split(','))
            for item in sidx_list:
                ordering = item.split(' ')
                if len(ordering) > 1:
                    order_by = u"{0}{1}".format(ordering[1] == 'desc' and '-' or '', ordering[0])
                else:
                    order_by = u"{0}{1}".format(sord == 'desc' and '-' or '', ordering[0])
                order_by_list.append(order_by)
            try:
                items = items.order_by(*order_by_list)
            except FieldError:
                pass
        return items

    def get_paginate_by(self, request):
        rows = request.GET.get('rows', self.get_config(False)['rowNum'])
        try:
            paginate_by = int(rows)
        except ValueError:
            paginate_by = 10
        return paginate_by

    def paginate_items(self, request, items):
        paginate_by = self.get_paginate_by(request)
        if not paginate_by:
            return None, None, items

        paginator = Paginator(items, paginate_by,
                              allow_empty_first_page=self.allow_empty)
        page = request.GET.get('page', 1)

        try:
            page_number = int(page)
            page = paginator.page(page_number)
        except (ValueError, InvalidPage):
            page = paginator.page(1)
        return paginator, page, page.object_list

    def get_json(self, request):
        paginator, page, items = self.get_items(request)
        items = items.values(*self.get_field_names()) if items.count() > 0 else []
        data = {
            'page': int(page.number),
            'total': int(paginator.num_pages),
            'rows': [obj for obj in items],
            'records': int(paginator.count),
        }
        return json_encode(data)

    def get_default_config(self):
        config = {
            'datatype': 'json',
            'autowidth': True,
            'forcefit': True,
            'ignoreCase': True,
            'shrinkToFit': True,
            'jsonReader': {'repeatitems': False},
            'rowNum': 10,
            'rowList': [10, 25, 50, 100],
            'sortname': 'id',
            'viewrecords': True,
            'sortorder': "asc",
            'pager': self.pager_id,
            'altRows': True,
            'gridview': True,
            'height': 'auto',
            # 'multikey': 'ctrlKey',
            # 'multiboxonly': True,
            # 'multiselect': True,
            # 'toolbar': [False, 'bottom'],
            # 'userData': None,
            # 'rownumbers': False,
        }
        return config

    def get_url(self):
        return str(self.url)

    def get_caption(self):
        if self.caption is None:
            opts = self.get_model()._meta
            self.caption = opts.verbose_name_plural.capitalize()
        return self.caption

    def get_config(self, as_json=True):
        config = self.get_default_config()
        config.update(self.extra_config)
        config.update({
            'url': self.get_url(),
            'caption': self.get_caption(),
            'colModel': self.get_colmodels(),
        })
        if as_json:
            config = json_encode(config)
        return config

    def lookup_foreign_key_field(self, options, field_name):
        """Make a field lookup converting __ into real models fields"""
        if '__' in field_name:
            fk_name, field_name = field_name.split('__', 1)
            fields = [f for f in options.fields if f.name == fk_name]
            if len(fields) > 0:
                field_class = fields[0]
            else:
                raise FieldError('No field %s in %s' % (fk_name, options))
            foreign_model_options = field_class.rel.to._meta
            return self.lookup_foreign_key_field(foreign_model_options, field_name)
        else:
            return options.get_field(field_name)

    def get_colmodels(self):
        colmodels = []
        opts = self.get_model()._meta
        for field_name in self.get_field_names():
            try:
                field = self.lookup_foreign_key_field(opts, field_name)
                colmodel = self.field_to_colmodel(field, field_name)
            except FieldDoesNotExist:
                colmodel = {
                    'name': field_name,
                    'index': field_name,
                    'label': field_name,
                    'editable': False
                }
            override = self.colmodel_overrides.get(field_name)

            if override:
                colmodel.update(override)
            colmodels.append(colmodel)
        return colmodels

    def get_field_names(self):
        fields = self.fields
        if not fields:
            fields = [f.name for f in self.get_model()._meta.local_fields]
        return fields

    @staticmethod
    def field_to_colmodel(field, field_name):
        colmodel = {
            'name': field_name,
            'index': field.name,
            'label': field.verbose_name,
            'editable': True
        }
        return colmodel
