"""Decode a read-only test corpus. Never use this fixture in a deliverable."""
import base64,hashlib,sys
from pathlib import Path
source=Path(__file__).resolve().parent/'bootloader-fixture.b64'
data=base64.b64decode(source.read_bytes(),validate=False)
if len(data)!=15104 or hashlib.sha256(data).hexdigest()!='2a71d69b471e20c2bac7fb469f3c6a807b3ebee780e348e5889db0da849ca363':
 raise ValueError('Rollback corpus mismatch')
Path(sys.argv[1]).write_bytes(data)
