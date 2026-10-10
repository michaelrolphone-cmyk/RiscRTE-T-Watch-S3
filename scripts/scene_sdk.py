"""Stage one canonical SDK per translation unit; never mix pragma-once copies."""
from pathlib import Path
import shutil

def stage_sdk(runtime: Path, system: Path, output: Path) -> Path:
    include = output / "include"
    include.mkdir(parents=True, exist_ok=True)
    for part in ("app", "driver", "hardware"):
        for source in (runtime / "sdk" / part).glob("*.h"):
            destination = include / source.name
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                raise ValueError(f"Conflicting canonical SDK header: {source.name}")
            shutil.copyfile(source, destination)
    for name in ("RiscDisplayOutputV1.h", "RiscTouchV1.h", "RiscInputNavigationV1.h"):
        source = system / "lib/PortableApps/include" / name
        destination = include / name
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            raise ValueError(f"Conflicting presentation contract: {name}")
        shutil.copyfile(source, destination)
    # Scene is an optional provider contract; older Runtime SDKs need the
    # unchanged canonical header carried by System, not a Runtime change.
    for name in ("RiscSceneV1.h", "RiscSceneStateV1.h", "RiscSceneLifecycleV1.h"):
        if not (include / name).exists():
            shutil.copyfile(system / "sdk/app" / name, include / name)
    shutil.copyfile(system / "Services/scene_profile/SceneProfileV1.h", include / "SceneProfileV1.h")
    shutil.copyfile(system / "Services/text_input/SceneKeyboardV1.h", include / "SceneKeyboardV1.h")
    return include
