# Catalog v7 actual-window QA

Date: 2026-10-06

All new scenes were explicit synthetic demos shown by the read-only viewer on the assistant's cloud desktop. No private player save was read or changed, and no game actions were performed.

Verified actual window sizes: 1180×812 and 390×844. The desktop window manager initially auto-maximized Tk; unmaximizing restored the requested narrow dimensions.

- Cat and bee have different, recognizable artwork in catalog thumbnails, shop stage and detail portraits
- The cat's collected label and bee's discovered label are distinct; both show the correct already-public stories
- Unknown rows and detail modals reveal no name, species, rarity, category or story. They share the same neutral question mark and generic locked text
- After known detail → tab change → catalog → later page, unknown entries do not inherit stale names, artwork or stories
- Narrow paging through collected, discovered and unknown rows is readable with no overlapping text; the unknown modal remains masked
- A zero-discovery scene shows 0/24, a generic crate on the stage, and only masked catalog entries/details at both sizes
- After dismissing an overlay, clicks were checked after the viewer's 250 ms redraw; both known rows open correctly

All v7 test windows were closed and the original observer was restored visually unchanged. Temporary public JSON scenes, launch wrappers and headless images were removed after testing. No screenshots or playable demo data are distributed.
