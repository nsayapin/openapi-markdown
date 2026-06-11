import json
import os

import yaml
from jinja2 import Environment, FileSystemLoader, PackageLoader
from openapi_core import Spec
from warnings import warn
from collections import Iterable

def to_json(value):
    return json.dumps(value, indent=2)


def ref_to_link(ref, prefix):
    if not ref:
        return ""
    if ref.get('$ref'):
        return get_ref_schema_name(ref, prefix)
    elif ref.get('type'):
        return f"{ref['type']}"
    return ""

def ref_to_type(ref, prefix):
    if isinstance(ref.get('type'),list) and not isinstance(ref.get('type'),str):
        val = '['
        for type in ref.get('type'):
            if isinstance(type,str):
                val = val + type
#                 Добавляем maxLength для string
                #TODO
                if ref.get('maxLength') and type=='number' and ref.get('multipleOf'):
                    maxLength = ref.get('maxLength')
                    multipleOfLength = count_places(ref.get('multipleOf'))
                    intPartLength = maxLength - multipleOfLength - 1
                    val = str(val) +  '(' + str(intPartLength) + ',' + str(multipleOfLength) + ')'
                elif ref.get('maxLength') and (type == 'string' or type == 'number'):
                    val = str(val) + '(' + str(ref.get('maxLength')) + ')'
#                 Запятая между элементами, если это не последний
                if type != ref.get('type')[-1]:
                    val = val+ ','
        val = val+ ']'
        return val
#         Если указан тип oneOf
    elif ref.get('oneOf'):
        val = '['
        for type in ref.get('oneOf'):
            if type.get('$ref'):
                refname = get_ref_schema_name(type, prefix)
                val = val + refname
#                 if prefix:
#                     val = val +  f"[{schema_name}](#{prefix}-{schema_name})"
#                 else:
#                     val = val +  f"[{schema_name}](#{schema_name.lower()})"
            elif type.get('type'):
                typeVal = type.get('type')
                # type = string
                if ref.get('maxLength') and ref.get('type') == 'string':
                    val = val + str(typeVal) + '(' + str(ref.get('maxLength')) + ')'
                # type = multipleOf
                elif ref.get('type') == 'number' and ref.get('multipleOf'):
                    maxLength = ref.get('maxLength')
                    multipleOfLength = count_places(ref.get('multipleOf'))
                    intPartLength = maxLength - multipleOfLength - 1
                    val = val + str(typeVal) + '(' + str(intPartLength) + ',' + str(multipleOfLength) + ')'
                else:
                    val = val + str(typeVal)
            if type != ref.get('oneOf')[-1]:
                val = val+ ','
        val = val+ ']'
        return val
    else:
        if ref.get('type')=='array':
            refname = get_ref_schema_name(ref.get('items'), prefix)
            return ref.get('type') +  '(' + refname + ')'
        if ref.get('type') == 'number' and ref.get('multipleOf'):
            maxLength = ref.get('maxLength')
            multipleOfLength = count_places(ref.get('multipleOf'))
            intPartLength = maxLength - multipleOfLength - 1
            return ref.get('type')  + '(' + str(intPartLength) + ',' + str(multipleOfLength) + ')'
        if ref.get('maxLength'):
            return ref.get('type') + '(' + str(ref.get('maxLength')) + ')'
        elif ref.get('type') == 'array':
            return ref.get('type')
        else:
            return ref.get('type')

def get_ref_schema_name(ref, prefix):
    parts = ref['$ref'].split("/")
    schema_name = parts[-1]
    if prefix:
        return f"[{schema_name}](#{prefix}-{schema_name})"
    return f"[{schema_name}](#{schema_name.lower()})"


def ref_to_param(ref, spec_data):
    warn('ref_to_param is deprecated. Use ref_to_schema directly.', DeprecationWarning,
         stacklevel=2)
    return ref_to_schema(ref, spec_data)


def ref_to_schema(schema, spec_data):
    """Convert a schema reference to actual schema object, recursively resolving all
    nested references while preserving $ref."""
    if isinstance(schema, dict):
        if '$ref' in schema:
            # Get the referenced schema
            ref_path = schema['$ref'].split('/')
            current = spec_data
            for part in ref_path[1:]:  # Skip the first '#' element
                current = current[part]
            # Merge the referenced schema with the original, keeping $ref
            resolved = ref_to_schema(current, spec_data)
            return {**resolved, **schema}
        else:
            # Process all dictionary values recursively
            return {k: ref_to_schema(v, spec_data) for k, v in schema.items()}
    elif isinstance(schema, list):
        # Process all list items recursively
        return [ref_to_schema(item, spec_data) for item in schema]
    return schema


def to_markdown(api_file, output_file, templates_dir='templates', options={}):
    # Load the OpenAPI 3.0 specification file in either JSON or YAML format
    with open(api_file) as f:
        spec_data = json.load(f) if api_file.endswith(".json") else yaml.safe_load(f)
    # Resolve all references in the spec data
    # spec_data = ref_to_schema(spec_data, spec_data)
    # filter spec_data.paths if filter_paths option is provided
    if 'filter_paths' in options and options['filter_paths']:
        spec_data['paths'] = {
            k: v for k, v in spec_data['paths'].items()
            if any(k.startswith(prefix) for prefix in options['filter_paths'])
        }
    # Getting prefix in documentation
    if 'prefix' in options and options['prefix']:
        prefix = options['prefix']
    else:
        prefix = ''

    spec = Spec.from_dict(spec_data)
    # Load the Jinja2 template file
    if os.path.exists(templates_dir):
        env = Environment(loader=FileSystemLoader(templates_dir))
    else:
        env = Environment(loader=PackageLoader('openapi_markdown', templates_dir))
    env.filters['ref_to_link'] = ref_to_link
    env.filters['to_json'] = to_json
    env.filters['ref_to_param'] = ref_to_param
    env.filters['ref_to_schema'] = ref_to_schema
    env.filters['ref_to_type'] = ref_to_type
    template = env.get_template('api_doc_template.md.j2')
    rendered_template = (
        template.render(spec=spec,
                        ref_to_param=lambda ref: ref_to_param(ref, spec_data),
                        ref_to_schema=lambda ref: ref_to_schema(ref, spec_data),
                        ref_to_link=lambda ref,prefix: ref_to_link(ref, prefix),
                        ref_to_type=lambda ref,prefix: ref_to_type(ref, prefix),
                        get_schema_type=lambda ref,prefix: get_schema_type(ref, prefix), # Получение схемы типа
                        prefix=prefix)
    )
    with open(output_file, "w") as f:
        f.write(rendered_template)

# Количество символов после запятой в multipleOf
def count_places(number):
    num_str = str(number)  # Переводим в строку
    if '.' in num_str:
        return len(num_str.split('.')[1])  # Считаем длину после точки
    return 0

#  Осуществляет получение типа схемы
def get_schema_type(ref, spec_data):
    schema = ref.get('schema')
    # первая часть значений - тип
    returnValue = schema.get('type')
    # Если есть maxLength и multipleOf
    if schema.get('maxLength') and schema.get('multipleOf'):
        maxLength = schema.get('maxLength')
        multipleOfLength = count_places(schema.get('multipleOf'))
        intPartLength = maxLength - multipleOfLength - 1
        returnValue +=  '(' + str(intPartLength) + ',' + str(multipleOfLength) + ')'
    # Если есть только maxLength строковый
    elif schema.get('maxLength'):
        returnValue += '(' + str(schema.get('maxLength')) + ')'
    return returnValue