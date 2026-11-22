# Hanoi Midpoint

Find the fairest place in Hanoi for a group of friends to meet, by road travel time from where each person starts.

Open it: https://kn0220.github.io/hanoi-midpoint/

- Tap the map, or search a street, alley, building or address, once per friend.
- To move a pin, hold it for a moment, then drag. A swipe that starts on a pin moves the map, so nobody's pin is dragged by accident; every move can be undone.
- "Fairest" makes the longest ride as short as possible; "Least total" makes everyone's travel added together as small as possible.
- Everything runs in the browser. Ride times are off-peak estimates from road type and distance, with no live traffic.
- Vietnamese or English: the VI / EN switch is at the top. The page starts in Vietnamese when the browser lists Vietnamese among its languages, and remembers the choice in that browser.

## Files

- `index.html` – the page (built from `src/index.html` by `tools/site.py`).
- `hanoi-v3.json` – roads, cafés and map shapes for central Hanoi and the near suburbs. `hanoi-v3-places.json` – place names, house numbers and the street list for search. Each has a `.gz` copy made by `tools/site.py`.
- `hanoi-v2.json`, `hanoi-v2-places.json` – the same data in the earlier, larger packing. `tools/pack3.py` makes the v3 files from them; pages that were open before the change still read them.
- `tools/fetch.py`, `tools/build.py` – download OpenStreetMap data and pack it into the v2 files. `tools/pack3.py . .` then repacks them, with nothing dropped or rounded.
- `tools/crosscheck.py` – independent check of the page's answers.
- `tools/site.py` – builds `index.html` from `src/index.html`; give it a database address as the third argument to switch on live groups.
- `tools/mockdb.py` – a local stand-in for the database, for testing live groups without the real one.

## Live groups (optional)

With a database address set, the page shows "Invite the group" once you have put yourself on the map. One tap starts the group and opens the phone's share sheet (elsewhere it copies the invite); everyone who opens the link adds their own pin and name, and the meeting place updates on every screen. When someone taps another place in the list, or switches between café, food and bar, every screen follows; the pick lasts until a pin, the way of travelling or the goal changes. Up to 12 people per group.

Everyone, the organiser included, is first asked where they are coming from, and their own pin is marked "you". The page remembers their name, their last place and which pin is theirs in that browser only, so next time adding themselves is one tap.

It uses a Firebase Realtime Database through its plain web address, with no sign-in and no key. Anyone who has a group's link can see and change that group's pins, and groups cannot be listed, so a group is as private as its link.

A group lasts one day from the moment it is started. After that the database refuses to show or change it, and its pins are deleted: by the page of the next person who opens the site, and by a daily job (`.github/workflows/sweep.yml`). Only groups that have already ended can be listed or deleted this way. GitHub pauses scheduled jobs in a repository with no activity for 60 days; the job can be turned back on from the Actions tab.

This site is built with its database address set, so live groups are on. To point a copy at another database: create a Realtime Database, set the rules in `tools/firebase-rules.json`, then rebuild with

    python3 tools/site.py src . https://<your-database-address>

`tools/mockdb.py <port> <lifetime in ms>` is a local stand-in for the database that enforces the same rules, for testing with a short lifetime.

## Data use

A first visit downloads about 1.2 MB: the road map (1.06 MB), the fonts and the page. Place names, house numbers and the street list (0.44 MB) are downloaded the first time someone uses search or zooms in close, and not at all on a phone set to save data unless they search.

The page keeps both data files in the browser's own store, so later visits download no map data, also after the site is updated. That only holds while the file names stay the same: new data must get a new file name (`hanoi-v4.json`) and a new store name (`KEEP` in `src/index.html`), or people keep the old copy.

The site host compresses files lightly on the way out, so `tools/site.py` writes harder-compressed `.gz` copies and the page asks for those first. A browser that cannot unpack them itself gets the plain file.

## Languages

English sentences are written in `src/index.html`; the Vietnamese for each one is in the `VI` table near the top of its script, looked up by the English sentence. A sentence with no Vietnamese line is shown in English. Names, the copied plan and the invite line are written in the language of the person who sends them.

## Link preview

`og.png` is the picture shown when the link is pasted into a chat. To make it again: build a preview page of `src/index.html` next to `src/og.html`, open `og.html` at 1200 by 630 and take a screenshot. Chat apps keep the old picture for a link they have already seen; adding `?v=2` to the link makes them fetch it again.

## Data

Roads, places and addresses © OpenStreetMap contributors, available under the Open Database License (https://www.openstreetmap.org/copyright).
