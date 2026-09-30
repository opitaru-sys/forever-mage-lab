Game icons

These 36 px icons are Blizzard Entertainment's art, taken from Wowhead's image server
(https://wow.zamimg.com/images/wow/icons/medium/<name>.jpg). This is a non-commercial fan project.

ICONS.txt lists every icon the page uses; src/build.py embeds exactly those, and fails if one is missing.
Icon names come from the "icon" field of Wowhead Forever tooltip JSON (nether.wowhead.com/forever/tooltip/spell/<id>).
To add an icon: put its name in ICONS.txt, then run  python assets/icons/fetch_icons.py
