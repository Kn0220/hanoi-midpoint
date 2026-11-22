# Hanoi Midpoint

Find the fairest place in Hanoi for a group of friends to meet, by road travel time from where each person starts.

Open it: https://kn0220.github.io/hanoi-midpoint/

- Tap the map, or search a street, alley, building or address, once per friend.
- "Fairest" makes the longest ride as short as possible; "Least total" makes everyone's travel added together as small as possible.
- Everything runs in the browser. Ride times are off-peak estimates from road type and distance, with no live traffic.

## Files

- `index.html` – the page (built from `src/index.html` by `tools/site.py`).
- `hanoi-v2.json`, `hanoi-v2-places.json` – roads, places and addresses for central Hanoi and the near suburbs.
- `tools/fetch.py`, `tools/build.py` – download OpenStreetMap data and pack it into the two data files.
- `tools/crosscheck.py` – independent check of the page's answers.
- `tools/site.py` – builds `index.html` from `src/index.html`; give it a database address as the third argument to switch on live groups.
- `tools/mockdb.py` – a local stand-in for the database, for testing live groups without the real one.

## Live groups (optional)

With a database address set, the page shows "Plan together with a live link". One person starts a group and sends the link; everyone who opens it adds their own pin and name, and the meeting place updates on every screen. Up to 12 people per group.

It uses a Firebase Realtime Database through its plain web address, with no sign-in and no key. Anyone who has a group's link can see and change that group's pins, and groups cannot be listed, so a group is as private as its link.

This site is built with its database address set, so live groups are on. To point a copy at another database: create a Realtime Database, set the rules in `tools/firebase-rules.json`, then rebuild with

    python3 tools/site.py src . https://<your-database-address>

## Data

Roads, places and addresses © OpenStreetMap contributors, available under the Open Database License (https://www.openstreetmap.org/copyright).
