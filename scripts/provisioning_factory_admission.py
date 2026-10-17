import json
from package_provisioning import require

def factory_admission(run_cohort, before, after, elf_count, store_digest):
    """Factory admission and a causal negative control for the old cohort."""
    import copy
    boot = json.loads(after['boot.json'])
    old_boot = json.loads(before['boot.json'])
    grant = {'capability': 'storage.key-value', 'api': 1, 'instance_id': 6}
    home = [row for row in boot['app_capabilities'] if row['manifest'] == 'default.json']
    old_home = [row for row in old_boot['app_capabilities'] if row['manifest'] == 'default.json']
    require(len(home) == len(old_home) == 1 and grant in home[0]['grants'] and
            grant not in old_home[0]['grants'] and 'cohort_migration' not in old_boot,
            'Expected factory-only namespace authority change missing')
    require(any(row['manifest'] != 'default.json' and grant in row['grants']
                for row in old_boot['app_capabilities']), 'Namespace 6 was not already owned')
    rejected = run_cohort(before, after, False)
    require(rejected['prepared'] and not rejected['cohort_validated'] and rejected['elf_count'] == 0 and
            not rejected['hardware_calls'] and not rejected['storage_calls'],
            'Preserving transition was not rejected before ELF admission')
    # Change exactly the new grant in a disposable metadata control. Actual
    # packaged bytes retain the reviewed factory bootstrap grant unchanged.
    control_boot = copy.deepcopy(boot)
    next(row for row in control_boot['app_capabilities'] if row['manifest'] == 'default.json')['grants'].remove(grant)
    control = dict(after, **{'boot.json': (json.dumps(control_boot, sort_keys=True, indent=2) + '\n').encode()})
    authority_control = run_cohort(before, control, True)
    require(authority_control['prepared'] and authority_control['cohort_validated'] and
            authority_control['elf_count'] == elf_count and not authority_control['hardware_calls'] and
            not authority_control['storage_calls'], 'Authority-only control did not admit every ELF')
    result = run_cohort(after, after, True)
    require(result['prepared'] and result['cohort_validated'] and not result['hardware_calls'] and
            not result['storage_calls'] and result['elf_count'] == elf_count and result['active_store_sha256'] ==
            result['candidate_store_sha256'] == store_digest(after), 'Factory self-admission digest/count differs')
    require(rejected['active_store_sha256'] == store_digest(before) and
            rejected['candidate_store_sha256'] == result['candidate_store_sha256'], 'Negative transition digest differs')
    result['mode'] = 'factory-bootstrap-self-admission'
    result['preserving_transition'] = dict(rejected, expected_rejection=True,
        reason='Existing twatch-clock gains already-owned storage.key-value namespace 6 without migration authority.',
        runtime_guard='src/bootstrap/CohortRuntime.inc: used && !owned; !migrating',
        authority_only_control=authority_control,
        control_packaged=False)
    return result


