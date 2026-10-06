"""Build the current ABI2 boot store with pinned ESP-IDF format settings.

Only image construction changes: names, file contents and partition geometry
remain owned by the validated deployment. Historical ABI1 builders stay frozen.
"""
import hashlib
import importlib.util
from pathlib import Path, PurePosixPath
import tempfile

from read_only_spiffs import read_image

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / 'vendor/esp-idf-spiffs/spiffsgen.py'
GENERATOR_SHA = '5779792a4d98a12383233267511735769a201b5c2c79b582186a40c22b7c6466'
UPSTREAM = '38eeba213aa695aabfd6d89aa9f5078dbe5a94c3'
IMAGE_SIZE = 0x510000
# Match the pinned ESP32-S3 Arduino/IDF SDK and the existing mkspiffs reader.
CONFIG = dict(page_size=256, page_ix_len=2, block_size=4096, block_ix_len=2,
              meta_len=4, obj_name_len=32, obj_id_len=2, span_ix_len=2,
              packed=True, aligned=True, endianness='little', use_magic=True,
              use_magic_len=True, aligned_obj_ix_tables=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def build(store, size=IMAGE_SIZE):
    require(size == IMAGE_SIZE, 'Current bootfs requires the verified ABI2 geometry')
    require(store, 'Current bootfs cannot be empty')
    # Validate the entire input before writing any temporary files. The NUL
    # terminator is included in the fixed 32-byte SPIFFS object-name field.
    for name, content in store.items():
        require(isinstance(name, str) and name and '\x00' not in name and '\\' not in name,
                'Invalid bootfs member name')
        path = PurePosixPath(name)
        require(path.parts and name.isascii() and not path.is_absolute() and str(path) == name and
                '..' not in path.parts and len(('/' + name).encode('utf-8')) < 32,
                'Invalid or oversized bootfs member name: ' + name)
        require(isinstance(content, bytes), 'Bootfs members must be exact bytes')
    require(hashlib.sha256(GENERATOR.read_bytes()).hexdigest() == GENERATOR_SHA,
            'Pinned SPIFFS generator source differs')
    spec = importlib.util.spec_from_file_location('watch_pinned_spiffsgen', GENERATOR)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    fs = generator.SpiffsFS(size, generator.SpiffsBuildConfig(**CONFIG))
    with tempfile.TemporaryDirectory(prefix='current-bootfs-input-') as tmp:
        # Fixed sorting and the generator's zero metadata remove host directory
        # order and mtime from the image. It emits pages directly without GC.
        for index, (name, content) in enumerate(sorted(store.items())):
            source = Path(tmp) / str(index)
            source.write_bytes(content)
            fs.create_file('/' + name, str(source))
    free_blocks = fs.remaining_blocks
    require(free_blocks >= 2, 'Current bootfs lacks SPIFFS free-block reserve')
    image = fs.to_binary()
    require(len(image) == size and read_image(image, size) == store,
            'Current bootfs independent round trip differs')
    record = dict(generator='esp-idf-spiffsgen', upstream_commit=UPSTREAM,
                  generator_sha256=GENERATOR_SHA, config=CONFIG.copy(),
                  order='sorted ASCII path names', metadata='zero',
                  image_bytes=size, file_count=len(store),
                  payload_bytes=sum(map(len, store.values())),
                  occupied_blocks=len(fs.blocks), empty_blocks=free_blocks,
                  sha256=hashlib.sha256(image).hexdigest(),
                  independent_round_trip_verified=True)
    return image, record
