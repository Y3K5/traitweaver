"""Bounded XLSX inspection only: preserve cell coordinates; never execute formulas.

No guessed headers or biological field mapping. An explicit mapping needs review
after the actual workbook is accessible. No HTTP calls or external relationships.
"""
from pathlib import Path, PurePosixPath
import posixpath
import zipfile
from xml.etree import ElementTree as ET
from .core import digest, require

MAIN = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def inspect_workbook(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Workbook is unavailable or is a symlink')
    require(path.stat().st_size <= 50_000_000, 'Workbook exceeds 50 MB')
    raw = path.read_bytes()
    with zipfile.ZipFile(path) as z:
        require(sum(i.file_size for i in z.infolist()) <= 100_000_000, 'Expanded workbook exceeds 100 MB')
        require(len(z.infolist()) <= 5000, 'Too many ZIP entries')
        names = z.namelist()
        require(len(names) == len(set(names)), 'Duplicate ZIP entries')
        require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names), 'Unsafe ZIP entry')

        def xml(name):
            data = z.read(name)
            require(b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper(), 'XML entity declarations are forbidden')
            return ET.fromstring(data)

        strings = []
        if 'xl/sharedStrings.xml' in names:
            strings = [''.join(n.itertext()) for n in xml('xl/sharedStrings.xml')]
        rels = {}
        for n in xml('xl/_rels/workbook.xml.rels'):
            require(n.get('TargetMode') != 'External', 'External workbook relationship is not admitted')
            target = posixpath.normpath(posixpath.join('xl', n.get('Target', '').lstrip('/'))) if not n.get('Target', '').startswith('/') else n.get('Target').lstrip('/')
            require(target.startswith('xl/') and '..' not in PurePosixPath(target).parts, 'Unsafe sheet relationship')
            rels[n.get('Id')] = target
        sheets = []
        for sheet in xml('xl/workbook.xml').find(MAIN+'sheets'):
            rows = []
            target = rels[sheet.get(REL+'id')]
            for row in xml(target).iter(MAIN+'row'):
                cells = []
                for cell in row.findall(MAIN+'c'):
                    value = cell.findtext(MAIN+'v')
                    kind = cell.get('t')
                    if kind == 's':
                        value = strings[int(value)]
                    elif kind == 'inlineStr':
                        value = ''.join(cell.find(MAIN+'is').itertext())
                    cells.append({'coordinate': cell.get('r'), 'type': kind, 'value': value,
                                  'formula': cell.findtext(MAIN+'f'), 'formula_executed': False})
                rows.append({'row': row.get('r'), 'cells': cells})
            sheets.append({'name': sheet.get('name'), 'rows': rows})
    return {'schema': 'traitweaver.workbook-quarantine.v1', 'sha256': digest(raw),
            'file_name': path.name, 'sheets': sheets, 'biological_records_admitted': 0,
            'status': 'readable_pending_explicit_column_mapping'}
