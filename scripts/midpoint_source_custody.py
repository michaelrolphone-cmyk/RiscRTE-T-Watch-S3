"""Isolated, source-owned imports for the immutable Watch 1.0.6 derivation.

Do not replace live modules in sys.modules or sys.path. Each frozen module gets
an import function that resolves its historical local imports within this same
verified closure, including imports performed later inside functions.
"""
import builtins
import hashlib
import importlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'custody/midpoint-1.0.6'
SOURCE = '9c8ecf7e2e20bdda24e6f5fb97273ffd7797a94a'
PROVENANCE_SHA = 'b5ac94c83886e678cd4f70d484137c1d759bca9b886b1604d5b0a1a4f2e39bfe'


def verify(root=FROZEN):
    root = Path(root)
    raw = (root / 'PROVENANCE.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROVENANCE_SHA:
        raise ValueError('Frozen midpoint provenance changed')
    record = json.loads(raw)
    if record['commit'] != SOURCE:
        raise ValueError('Frozen midpoint source changed')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*')
              if p.is_file() and p != root / 'PROVENANCE.json'}
    if actual != set(record['files']):
        raise ValueError('Frozen midpoint inventory changed')
    for name, identity in record['files'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != identity['sha256']:
            raise ValueError('Frozen derivation source changed: ' + name)
    return record


class FrozenModules:
    def __init__(self, root=FROZEN):
        self.root = Path(root)
        self.record = verify(self.root)
        self.modules = {}
        # The original SPIFFS helper loads its generator by file path. Keep that
        # exact source path, but never read or write an ambient bytecode cache.
        self.importlib = ModuleType('importlib')
        self.importlib.__dict__.update(vars(importlib))
        self.importlib.util = ModuleType('importlib.util')
        self.importlib.util.__dict__.update(vars(importlib.util))
        self.importlib.util.spec_from_file_location = self.source_spec

    @staticmethod
    def source_spec(name, location, *args, **kwargs):
        class SourceOnlyLoader(importlib.machinery.SourceFileLoader):
            def get_code(self, fullname):
                return self.source_to_code(self.get_data(self.path), self.path)
        return importlib.util.spec_from_file_location(
            name, location, *args, loader=SourceOnlyLoader(name, str(location)), **kwargs)

    def load(self, name):
        if name not in self.record['modules']:
            raise ImportError('Undeclared frozen midpoint module: ' + name)
        if name in self.modules:
            return self.modules[name]
        path = self.root / 'scripts' / (name + '.py')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.record['files']['scripts/' + name + '.py']['sha256']:
            raise ValueError('Frozen derivation source changed: scripts/' + name + '.py')
        module = ModuleType('_watch_midpoint_' + name)
        module.__file__ = str(path)
        module.__package__ = ''
        module.__dict__['__builtins__'] = {**vars(builtins), '__import__': self.import_module}
        self.modules[name] = module
        try:
            exec(compile(raw, str(path), 'exec'), module.__dict__)
        except BaseException:
            del self.modules[name]
            raise
        return module

    def import_module(self, name, globals=None, locals=None, fromlist=(), level=0):
        if not level and name in self.record['modules']:
            return self.load(name)
        if not level and name in ('importlib', 'importlib.util'):
            return self.importlib.util if name == 'importlib.util' and fromlist else self.importlib
        return builtins.__import__(name, globals, locals, fromlist, level)
