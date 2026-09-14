"""date-fields-v1: independent Y/M/D values, fixed three-field denominator."""
import re
from datetime import date

FIELDS = ('year', 'month', 'day')
POLICY = 'date-fields-v1'


def field_values(row):
    values = {}
    for name, width, maximum in (('year', 4, 2099), ('month', 2, 12), ('day', 2, 31)):
        value = row.get(name)
        if value != 'NONE' and (not isinstance(value, str) or
                not re.fullmatch(r'[0-9]{%d}' % width, value) or not 1 <= int(value) <= maximum):
            raise ValueError('Invalid ' + name + ' field: ' + repr(value))
        values[name] = value
    return values


def serialize_fields(row):
    values = field_values(row)
    y, m, d = (values[k] for k in FIELDS)
    if m != 'NONE' and d != 'NONE':
        date(int(y) if y != 'NONE' else 2000, int(m), int(d))
    result = '-'.join(values[k] for k in FIELDS)
    return dict(values, final_date='NONE' if result == 'NONE-NONE-NONE' else result)


def fields_from_date(value):
    if value is None or value in ('NONE', 'NONE-NONE-NONE'):
        return serialize_fields(dict.fromkeys(FIELDS, 'NONE'))
    if not isinstance(value, str) or len(value.split('-')) != 3:
        raise ValueError('Invalid date: ' + repr(value))
    return serialize_fields(dict(zip(FIELDS, value.split('-'))))


def compliant_row(row):
    try:
        expected = serialize_fields(row)
    except ValueError:
        return False
    partial = any(expected[k] == 'NONE' for k in FIELDS)
    return (list(row) == ['image_id', *FIELDS, 'final_date'] and
            (row.get('final_date') == expected['final_date'] or partial and row.get('final_date') == 'NONE'))
