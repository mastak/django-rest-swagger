"""Generates API documentation by introspection."""
import rest_framework
from rest_framework import viewsets
from rest_framework.serializers import BaseSerializer

from .introspectors import APIViewIntrospector, \
    WrappedAPIViewIntrospector, \
    ViewSetIntrospector, BaseMethodIntrospector, IntrospectorHelper, \
    get_default_value, get_data_type
from .compat import OrderedDict


class DocumentationGenerator(object):
    # Serializers defined in docstrings
    explicit_serializers = set()

    # Serializers defined in fields
    fields_serializers = set()

    # Response classes defined in docstrings
    explicit_response_types = dict()

    def generate(self, apis):
        """
        Returns documentation for a list of APIs
        """
        api_docs = []
        for api in apis:
            api_docs.append({
                'description': IntrospectorHelper.get_view_description(api['callback']),
                'path': api['path'],
                'operations': self.get_operations(api, apis),
            })

        return api_docs

    def get_introspector(self, api, apis):
        path = api['path']
        pattern = api['pattern']
        callback = api['callback']
        if callback.__module__ == 'rest_framework.decorators':
            return WrappedAPIViewIntrospector(callback, path, pattern)
        elif issubclass(callback, viewsets.ViewSetMixin):
            patterns = [a['pattern'] for a in apis
                        if a['callback'] == callback]
            return ViewSetIntrospector(callback, path, pattern,
                                       patterns=patterns)
        else:
            return APIViewIntrospector(callback, path, pattern)

    def get_operations(self, api, apis=None):
        """
        Returns docs for the allowed methods of an API endpoint
        """
        if apis is None:
            apis = [api]
        operations = []

        introspector = self.get_introspector(api, apis)

        for method_introspector in introspector:
            if not isinstance(method_introspector, BaseMethodIntrospector) or \
                    method_introspector.get_http_method() == "OPTIONS":
                continue  # No one cares. I impose JSON.

            doc_parser = method_introspector.get_yaml_parser()

            serializer = self._get_method_serializer(method_introspector)

            response_type = self._get_method_response_type(
                doc_parser, serializer, introspector, method_introspector)

            operation = {
                'method': method_introspector.get_http_method(),
                'summary': method_introspector.get_summary(),
                'nickname': method_introspector.get_nickname(),
                'notes': method_introspector.get_notes(),
                'type': response_type,
            }

            if doc_parser.yaml_error is not None:
                operation['notes'] += "<pre>YAMLError:\n {err}</pre>".format(
                    err=doc_parser.yaml_error)

            response_messages = doc_parser.get_response_messages()
            parameters = doc_parser.discover_parameters(
                inspector=method_introspector)

            if parameters:
                operation['parameters'] = parameters

            if response_messages:
                operation['responseMessages'] = response_messages

            operations.append(operation)

        return operations

    def get_models(self, apis):
        """
        Builds a list of Swagger 'models'. These represent
        DRF serializers and their fields
        """
        serializers = self._get_serializer_set(apis)
        serializers.update(self.explicit_serializers)
        serializers.update(
            self._find_field_serializers(serializers)
        )

        models = {}

        for serializer in serializers:
            data = self._get_serializer_fields(serializer)

            # Register 2 models with different subset of properties suitable
            # for data reading and writing.
            # i.e. rest framework does not output write_only fields in response
            # or require read_only fields in complex input.

            serializer_name = IntrospectorHelper.get_serializer_name(serializer)
            # Writing
            # no readonly fields
            w_name = "Write{serializer}".format(serializer=serializer_name)

            w_properties = OrderedDict((k, v) for k, v in data['fields'].items()
                                       if k not in data['read_only'])

            models[w_name] = {
                'id': w_name,
                'required': [i for i in data['required'] if i in w_properties.keys()],
                'properties': w_properties,
            }

            # Reading
            # no write_only fields
            r_name = serializer_name

            r_properties = OrderedDict((k, v) for k, v in data['fields'].items()
                                       if k not in data['write_only'])

            models[r_name] = {
                'id': r_name,
                'required': [i for i in r_properties.keys()],
                'properties': r_properties,
            }

            # Enable original model for testing purposes
            # models[serializer_name] = {
            #     'id': serializer_name,
            #     'required': data['required'],
            #     'properties': data['fields'],
            # }

        models.update(self.explicit_response_types)
        models.update(self.fields_serializers)
        return models

    def _get_method_serializer(self, method_inspector):
        """
        Returns serializer used in method.
        Registers custom serializer from docstring in scope.

        Serializer might be ignored if explicitly told in docstring
        """
        serializer = method_inspector.get_response_serializer_class()
        doc_parser = method_inspector.get_yaml_parser()

        if doc_parser.get_response_type() is not None:
            # Custom response class detected
            return None

        if doc_parser.should_omit_serializer():
            serializer = None

        return serializer

    def _get_method_response_type(self, doc_parser, serializer,
                                  view_inspector, method_inspector):
        """
        Returns response type for method.
        This might be custom `type` from docstring or discovered
        serializer class name.

        Once custom `type` found in docstring - it'd be
        registered in a scope
        """
        response_type = doc_parser.get_response_type()
        if response_type is not None:
            # Register class in scope
            view_name = view_inspector.callback.__name__
            view_name = view_name.replace('ViewSet', '')
            view_name = view_name.replace('APIView', '')
            view_name = view_name.replace('View', '')
            response_type_name = "{view}{method}Response".format(
                view=view_name,
                method=method_inspector.method.title().replace('_', '')
            )
            self.explicit_response_types.update({
                response_type_name: {
                    "id": response_type_name,
                    "properties": response_type
                }
            })
            return response_type_name
        else:
            serializer_name = IntrospectorHelper.get_serializer_name(serializer)
            if serializer_name is not None:
                return serializer_name

            return None

    def _get_serializer_set(self, apis):
        """
        Returns a set of serializer classes for a provided list
        of APIs
        """
        serializers = set()

        for api in apis:
            introspector = self.get_introspector(api, apis)
            for method_introspector in introspector:
                serializer = self._get_method_serializer(method_introspector)
                if serializer is not None:
                    serializers.add(serializer)

        return serializers

    def _find_field_serializers(self, serializers, found_serializers=set()):
        """
        Returns set of serializers discovered from fields
        """
        def get_thing(field, key):
            if rest_framework.VERSION >= '3.0.0':
                from rest_framework.serializers import ListSerializer
                if isinstance(field, ListSerializer):
                    return key(field.child)
            return key(field)

        serializers_set = set()
        for serializer in serializers:
            fields = serializer().get_fields()
            for name, field in fields.items():
                if isinstance(field, BaseSerializer):
                    serializers_set.add(get_thing(field, lambda f: f))
                    if field not in found_serializers:
                        serializers_set.update(
                            self._find_field_serializers(
                                (get_thing(field, lambda f: f.__class__),),
                                serializers_set))

        return serializers_set

    def _get_serializer_fields(self, serializer):
        """
        Returns serializer fields in the Swagger MODEL format
        """
        if serializer is None:
            return

        if hasattr(serializer, '__call__'):
            fields = serializer().get_fields()
        else:
            fields = serializer.get_fields()

        data = OrderedDict({
            'fields': OrderedDict(),
            'required': [],
            'write_only': [],
            'read_only': [],
        })
        for name, field in fields.items():
            if getattr(field, 'write_only', False):
                data['write_only'].append(name)

            if getattr(field, 'read_only', False):
                data['read_only'].append(name)

            if getattr(field, 'required', False):
                data['required'].append(name)

            data_type = get_data_type(field)

            # guess format
            data_format = 'string'
            if data_type in BaseMethodIntrospector.PRIMITIVES:
                data_format = BaseMethodIntrospector.PRIMITIVES.get(data_type)[0]

            description = getattr(field, 'help_text', '')
            if not description or description.strip() == '':
                description = None
            f = {
                'description': description,
                'type': data_type,
                'format': data_format,
                'required': getattr(field, 'required', False),
                'defaultValue': get_default_value(field),
                'readOnly': getattr(field, 'read_only', None),
            }

            # Min/Max values
            max_val = getattr(field, 'max_val', None)
            min_val = getattr(field, 'min_val', None)
            if max_val is not None and data_type == 'integer':
                f['minimum'] = min_val

            if max_val is not None and data_type == 'integer':
                f['maximum'] = max_val

            # ENUM options
            if get_data_type(field) == 'multiple choice' \
                    and isinstance(field.choices, list):
                f['enum'] = [k for k, v in field.choices]

            # Support for complex types
            if isinstance(field, BaseSerializer):
                field_serializer = IntrospectorHelper.get_serializer_name(field)

                if getattr(field, 'write_only', False):
                    field_serializer = "Write{}".format(field_serializer)

                f['type'] = field_serializer
                if rest_framework.VERSION < '3.0.0':
                    has_many = field.many
                else:
                    from rest_framework.serializers import ListSerializer
                    has_many = isinstance(field, ListSerializer)
                if has_many:
                    f['type'] = 'array'
                    if data_type in BaseMethodIntrospector.PRIMITIVES:
                        f['items'] = {'type': data_type}
                    else:
                        f['items'] = {'$ref': field_serializer}

            # memorize discovered field
            data['fields'][name] = f

        return data
