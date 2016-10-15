import operator
import random
import string
from hashlib import sha512


SIMPLE_CHARS = string.ascii_letters + string.digits


def get_random_string(length=24):
    return ''.join(random.choice(SIMPLE_CHARS) for i in xrange(length))


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
    lengths = map(len, columns)
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
