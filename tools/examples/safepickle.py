"""Load downloaded pickle / joblib files that should hold only dicts, lists and numpy arrays.

Dataset pickles are untrusted: a plain pickle.load can run any code. find_class here allows only the names needed to
rebuild numpy arrays (and joblib's array wrapper) and raises for anything else, nested object arrays included
(joblib >= 1.5 routes those through the outer find_class).
"""
import pickle

ALLOWED = {('numpy.core.multiarray', '_reconstruct'), ('numpy._core.multiarray', '_reconstruct'), ('numpy', 'ndarray'),
           ('numpy', 'dtype'), ('numpy.core.multiarray', 'scalar'), ('numpy._core.multiarray', 'scalar'),
           ('joblib.numpy_pickle', 'NumpyArrayWrapper'), ('collections', 'OrderedDict'), ('builtins', 'dict'), ('builtins', 'list')}


def _check(module, name):
    if (module, name) not in ALLOWED:
        raise pickle.UnpicklingError(f'refusing to load {module}.{name}')


class Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        _check(module, name)
        return super().find_class(module, name)


def load(path):
    """a plain pickle or a joblib dump (compressed or not) -> the object"""
    try:
        from joblib import numpy_pickle as jp
    except ImportError:
        with open(path, 'rb') as f:
            return Unpickler(f).load()

    class JoblibUnpickler(jp.NumpyUnpickler):
        def find_class(self, module, name):
            _check(module, name)
            return super().find_class(module, name)

    with open(path, 'rb') as f, jp._validate_fileobject_and_memmap(f, path, None) as (fobj, _):
        return JoblibUnpickler(path, fobj, True).load()
