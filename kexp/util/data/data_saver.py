import time
import h5py
import numpy as np
import os
from operator import setitem
from artiq import __version__ as artiq_version

class DataSaver:

    datapath = os.getenv("data")

    def __init__(self):
        self.start_time = time.localtime(time.time())
        self.filename = time.strftime("%Y-%m-%d-%H-%M-%S", start_time)
        self.data = dict()

    def set(self,key,value):
        self.data[key] = value

    def write_hdf5(self, f):
        datasets_group = f.create_group("datasets")
        for k, v in self.local.items():
            _write(datasets_group, k, v)

    def _get_mutation_target(self, key):
        target = self.local.get(key, None)
        if key in self._broadcaster.raw_view:
            if target is not None:
                assert target is self._broadcaster.raw_view[key][1]
            return self._broadcaster[key][1]
        if target is None:
            raise KeyError("Cannot mutate nonexistent dataset '{}'".format(key))
        return target

    def mutate(self, key, index, value):
        target = self._get_mutation_target(key)
        if isinstance(index, tuple):
            if isinstance(index[0], tuple):
                index = tuple(slice(*e) for e in index)
            else:
                index = slice(*index)
        setitem(target, index, value)

    def append_to(self, key, value):
        self._get_mutation_target(key).append(value)

    def write_results(self,):
        filename = "{:09}-{}.h5".format(rid, exp.__name__)
        with h5py.File(filename, "w") as f:
            self.write_hdf5(f)
            f["artiq_version"] = artiq_version
            f["start_time"] = self.start_time

def _write(group, k, v):
        # Add context to exception message when the user writes a dataset that is
        # not representable in HDF5.
        try:
            group[k] = v
        except TypeError as e:
            raise TypeError("Error writing dataset '{}' of type '{}': {}".format(
                k, type(v), e))