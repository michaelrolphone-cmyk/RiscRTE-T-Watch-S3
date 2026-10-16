# Expanded Watch source recovery

The execution filesystem was replaced at 2026-10-13 11:44 UTC. Public Runtime
95cd11945ed52be6790e0372dacd1316a9b908d5 and its green CI run 38391489340 remain
available. This checkpoint restores the product expansion, exact component
staging, source-bound admission and factory sealing source from authored patch
content onto public product 0952e1e6c1b7e77faffa1ef0e2123378f0dcade6.

Original local commits 5fdfcf8, 4697f3b, 0e64c41, 11e81ec and c9e05de were not
published before the reset. Reconstructed files are retested; individual byte
identity with those lost local commits is not independently claimed. The exact
component inventory SHA and all app/provider/native source gates are retained.
The recovered 1.1.21-r1 factory BIN, shared Home pair and shared UI target inputs
are retrieved from their existing Library or public CI artifacts and rehashed.

This is not a flashable build. Full target, exact store admission and factory
readback must run after restoration. A confirmed generic compatibility blocker
remains: the recovered Runtime manifest whitelist rejects Contexts' optional
app.catalog declaration. The repair must preserve shared app binaries and
owner-grant enforcement rather than removing the declaration.

The approved factory layout preserves all 25 apps and 512 KiB AppData capacity.
FULL FACTORY BIN at 0x0 ERASES CURRENT SETTINGS, NVS and app-data.
No automatic flashing; not an OTA migration.
