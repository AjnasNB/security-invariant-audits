"""Data-only decoder, intended to run in the restricted no-network container."""
import io
import json
import pickle
import pickletools
from pathlib import Path
import hashlib


class PlainDataUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise pickle.UnpicklingError(f"Object constructors are prohibited: {module}.{name}")

    def persistent_load(self, pid):
        raise pickle.UnpicklingError("Persistent IDs are prohibited")


def decode(path):
    raw = Path(path).read_bytes()
    prohibited = {"GLOBAL", "STACK_GLOBAL", "REDUCE", "BUILD", "OBJ", "INST", "NEWOBJ", "NEWOBJ_EX",
                  "EXT1", "EXT2", "EXT4", "PERSID", "BINPERSID"}
    counts = {}
    for operation, value, offset in pickletools.genops(raw):
        counts[operation.name] = counts.get(operation.name, 0) + 1
        if operation.name in prohibited:
            raise ValueError(f"Unsafe pickle opcode {operation.name} at {offset}")
    value = PlainDataUnpickler(io.BytesIO(raw)).load()
    json.dumps(value)
    return value, {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw),
                   "opcode_counts": counts, "constructor_opcodes": 0}


if __name__ == "__main__":
    data, audit_data = decode("/task/dataset/text/dataset.pkl")
    keys, audit_keys = decode("/task/dataset/text/dataset-key.pkl")
    if len(data) != len(keys):
        raise ValueError("JailGuard data/key count mismatch")
    print(json.dumps({"data": data, "keys": keys, "audit": {"data": audit_data, "keys": audit_keys}}))
