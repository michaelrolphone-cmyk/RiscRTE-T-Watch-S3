"""Capability-only metadata transform for apps with existing unavailable UI.

No ELF edits or implicit grants. Absent capability names must come from the
product's reviewed provider inventory, never a runtime probe during packaging.
"""
import copy

OPTIONAL = {
    'lora_messages': {'radio.lora'},
    'watch-bringup': {'board.battery', 'rtc.clock', 'motion.accel', 'haptic.effect'},
}

def provision(manifest, policy, absent=()):
    manifest, policy = copy.deepcopy(manifest), copy.deepcopy(policy)
    selected = OPTIONAL.get(manifest['id'], set())
    absent = set(absent)
    if absent - selected:
        raise ValueError('No unavailable UI contract for omitted capability')
    moved = [r for r in manifest['requires'] if r['capability'] in selected]
    manifest['requires'] = [r for r in manifest['requires'] if r['capability'] not in selected]
    optional = manifest.get('optional', []) + moved
    keys = [(r['capability'], r['api']) for r in optional + manifest['requires']]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate declarations')
    if optional:
        manifest['optional'] = optional
    policy['grants'] = [g for g in policy['grants'] if g['capability'] not in absent]
    return manifest, policy

def apply_store(store, absent=()):
    """Transform an unsealed staging directory, preserving every ELF byte."""
    import json
    from pathlib import Path
    store = Path(store)
    boot = json.loads((store / 'boot.json').read_text())
    changes = []
    for i, policy in enumerate(boot['app_capabilities']):
        path = Path(policy['manifest'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Invalid manifest path')
        manifest = json.loads((store / path).read_text())
        caps = OPTIONAL.get(manifest['id'])
        if not caps:
            continue
        changed, new_policy = provision(manifest, policy, set(absent) & caps)
        if changed != manifest or new_policy != policy:
            changes.append((path, changed))
            boot['app_capabilities'][i] = new_policy
    for path, manifest in changes:
        (store / path).write_text(json.dumps(manifest, separators=(',', ':'))+'\n')
    if changes:
        (store / 'boot.json').write_text(json.dumps(boot, separators=(',', ':'))+'\n')
    return [str(path) for path, _ in changes]

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--store', required=True)
    p.add_argument('--absent', action='append', default=[], choices=sorted(set().union(*OPTIONAL.values())))
    a=p.parse_args()
    print(apply_store(a.store, a.absent))
