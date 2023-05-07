import json
import os
from typing import Union
from uuid import uuid4
from threading import RLock
import operator
import random
import string
from hashlib import sha512

from flask import current_app


SIMPLE_CHARS = string.ascii_letters + string.digits


def get_random_string(length=24):
    return ''.join(random.choice(SIMPLE_CHARS) for i in range(length))


random_string = get_random_string


def get_random_hash(length=24):
    sha = sha512()
    sha.update(get_random_string())
    return sha.hexdigest()[:length]


def intify(value, default=0):
    try:
        return int(value)
    except:
        return default


def listify(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    else:
        return [value]


def remove_empty_rows(*columns):
    lengths = list(map(len, columns))
    assert all(i == lengths[0] for i in lengths), "Not all columns are the same length"
    keep = []
    for i in range(lengths[0]):
        drop = False
        for column in columns:
            if column[i] in [None, "", " "]:
                drop = True
                break
        if not drop:
            keep.append(i)
    if len(keep) == 0:
        return [[] for i in lengths]
    op = operator.itemgetter(*keep)
    return [listify(op(column)) for column in columns]


_unique_name_lock = RLock()


def touch_file(path):
    open(path, 'wb').close()


def make_unique_name(template):
    i = 1
    with _unique_name_lock:
        while os.path.exists(template % (str(i),)) and i < (2 ** 16):
            i += 1
        if i >= (2 ** 16):
            result = template % (uuid4().int,)
        else:
            result = template % (i,)
        touch_file(result)
        return result


def float_or(numval: Union[float, str], alt: float) -> float:
    if isinstance(numval, float):
        return numval
    if not numval:
        return alt
    numval = json.loads(numval)
    if numval is None:
        return alt
    if not isinstance(numval, (float, int)):
        current_app.logger.warn(
            "Numerical value expected, got %r, returning alternative %r",
            numval,
            alt
        )
        return alt
    return numval


def float_or_infinity(numcode):
    return float_or(numcode, float('inf'))


def try_int(value: str):
    try:
        return int(value)
    except Exception:
        current_app.logger.error(
            "Failed to parse integer from %r, returning 1", value, exc_info=1)
        return 1
