# Watch Model Viewer integration

The 1.1.0 canvas development candidate adds Model Viewer 1.3.0 to the complete
Watch app set, including the corrected Contexts scene app and Lists. Hollow
Trail is intentionally selected only in the X4 product. Accepted release
metadata and historical build lanes are unchanged.

Run Utilities' `build_canvas_apps.py --target watch` and this repository's
`scripts/build_canvas_launchers.py`. The launcher catalogue contains 23
visible entries; clock/default/Springboard bookkeeping leaves 25 app policies.
Use the Watch System Apps canvas catalogue source (a continuation of the
Watch temporal branch), not X4's different resident adapter configuration.
Runtime 0.2.4 has a 28-app PSRAM metadata bound and 28-provider/44-grant graph;
the full candidate selects 27 providers and the existing 24-row policy profile.
No app gets extra live grants or shared storage authority.

The viewer uses display 5, raw touch 6 and private AppData namespace 64.
It starts with a cube, renders at 240x240, and provides Rotate/Pan/Zoom,
Shaded/Wire and double-tap reset. Saved OBJ/STL models can be provisioned as
`model.obj`/`model.stl` in that namespace, up to 64 KiB each. The Watch has no
SD volume or new wireless uploader in this candidate. A missing saved file
shows an error without discarding the visible model.

Utilities' stage/package scripts preserve the selected baseline files, verify
all executable imports against the new native ELF and run the full graph
through ordinary and sanitizer admission before assembling the image.
The full 16 MiB image at 0x0 overwrites internal settings and AppData; it is
not a preserving update. No physical Watch test is claimed.
