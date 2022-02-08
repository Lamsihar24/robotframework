#  Copyright 2008-2015 Nokia Networks
#  Copyright 2016-     Robot Framework Foundation
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import os.path

from robot.errors import DataError
from robot.running import ArgInfo, ArgumentSpec
from robot.utils import ET, ETSource

from .datatypes import EnumMember, TypedDictItem, TypeDoc, Usage
from .model import LibraryDoc, KeywordDoc


class XmlDocBuilder:

    def build(self, path):
        spec = self._parse_spec(path)
        libdoc = LibraryDoc(name=spec.get('name'),
                            type=spec.get('type').upper(),
                            version=spec.find('version').text or '',
                            doc=spec.find('doc').text or '',
                            scope=spec.get('scope'),
                            doc_format=spec.get('format') or 'ROBOT',
                            source=spec.get('source'),
                            lineno=int(spec.get('lineno')) or -1)
        libdoc.inits = self._create_keywords(spec, 'inits/init', libdoc.source)
        libdoc.keywords = self._create_keywords(spec, 'keywords/kw', libdoc.source)
        # RF >= 5 have 'types', RF >= 4 have 'datatypes', older/custom may have neither.
        if spec.find('types'):
            libdoc.types = self._parse_types(spec)
        else:
            libdoc.types = self._parse_data_types(spec)
        return libdoc

    def _parse_spec(self, path):
        if not os.path.isfile(path):
            raise DataError("Spec file '%s' does not exist." % path)
        with ETSource(path) as source:
            root = ET.parse(source).getroot()
        if root.tag != 'keywordspec':
            raise DataError("Invalid spec file '%s'." % path)
        version = root.get('specversion')
        if version not in ('3', '4'):
            raise DataError(f"Invalid spec file version '{version}'. "
                            f"Supported versions are 3 and 4.")
        return root

    def _create_keywords(self, spec, path, lib_source):
        return [self._create_keyword(elem, lib_source) for elem in spec.findall(path)]

    def _create_keyword(self, elem, lib_source):
        # "deprecated" attribute isn't read because it is read from the doc
        # automatically. That should probably be changed at some point.
        return KeywordDoc(name=elem.get('name', ''),
                          args=self._create_arguments(elem),
                          doc=elem.find('doc').text or '',
                          shortdoc=elem.find('shortdoc').text or '',
                          tags=[t.text for t in elem.findall('tags/tag')],
                          source=elem.get('source') or lib_source,
                          lineno=int(elem.get('lineno', -1)))

    def _create_arguments(self, elem):
        spec = ArgumentSpec()
        setters = {
            ArgInfo.POSITIONAL_ONLY: spec.positional_only.append,
            ArgInfo.POSITIONAL_ONLY_MARKER: lambda value: None,
            ArgInfo.POSITIONAL_OR_NAMED: spec.positional_or_named.append,
            ArgInfo.VAR_POSITIONAL: lambda value: setattr(spec, 'var_positional', value),
            ArgInfo.NAMED_ONLY_MARKER: lambda value: None,
            ArgInfo.NAMED_ONLY: spec.named_only.append,
            ArgInfo.VAR_NAMED: lambda value: setattr(spec, 'var_named', value),
        }
        for arg in elem.findall('arguments/arg'):
            name_elem = arg.find('name')
            if name_elem is None:
                continue
            name = name_elem.text
            setters[arg.get('kind')](name)
            default_elem = arg.find('default')
            if default_elem is not None:
                spec.defaults[name] = default_elem.text or ''
            type_elems = arg.findall('type')
            if not spec.types:
                spec.types = {}
            spec.types[name] = tuple(t.text for t in type_elems)
        return spec

    def _parse_types(self, spec):
        for elem in spec.findall('types/type'):
            doc = TypeDoc(elem.get('type'), elem.get('name'), elem.find('doc').text)
            doc.usages = self._parse_usages(elem)
            if doc.type == TypeDoc.ENUM:
                doc.members = self._parse_members(elem)
            if doc.type == TypeDoc.TYPED_DICT:
                doc.items = self._parse_items(elem)
            yield doc

    def _parse_usages(self, elem):
        return [Usage(usage.get('kw'), [a.text for a in usage.findall('arg')])
                for usage in elem.findall('usages/usage')]

    def _parse_members(self, elem):
        return [EnumMember(member.get('name'), member.get('value'))
                for member in elem.findall('members/member')]

    def _parse_items(self, elem):
        def get_required(item):
            required = item.get('required', None)
            return None if required is None else required == 'true'
        return [TypedDictItem(item.get('key'), item.get('type'), get_required(item))
                for item in elem.findall('items/item')]

    # Code below used for parsing legacy 'datatypes'.

    def _parse_data_types(self, spec):
        for elem in spec.findall('datatypes/enums/enum'):
            yield self._create_enum_doc(elem)
        for elem in spec.findall('datatypes/typeddicts/typeddict'):
            yield self._create_typed_dict_doc(elem)

    def _create_enum_doc(self, elem):
        return TypeDoc(TypeDoc.ENUM, elem.get('name'), elem.find('doc').text,
                       members=self._parse_members(elem))

    def _create_typed_dict_doc(self, elem):
        return TypeDoc(TypeDoc.TYPED_DICT, elem.get('name'), elem.find('doc').text,
                       items=self._parse_items(elem))