"""
Category groups, their colours and names, and the avatar palette.
This is the ONE place to change them.

The backend has 20 categories (taxonomy.py). The site shows them as 10
broader GROUPS. CATEGORY_GROUP maps each backend category (by slug, made from
category_name) to a group. If a category is added or renamed in the backend,
add or rename it here too; anything unknown falls back to grey "Other".

Each group has a LIGHT and a DARK set of colours (the site has both themes):
  strong   the category hue. Light theme: used as-is (the original look).
           Dark theme: lifted by on_dark() so deep hues stay visible.
           Used for the home page boxes' --cat (dots, borders, soft tints).
  bg, fg   pill background and text. GROUPS holds the original light pair
           (fg on bg >= 4.5 : 1); DARK_PILLS holds the dark pair (>= 8.3 : 1).

Pages never get hex values directly: category_style() and the home cards hand
out CSS variables (var(--cat-science-bg) …), and theme_css() writes their light
and dark values once, in base.html. So switching theme needs no page reload.

Sport and Recreation are both green, so pages always show the group NAME next
to its colour: never rely on colour alone.
"""

import re

# key: (name, strong, light bg, light fg) in the order the home page shows them.
# These are the ORIGINAL light colours (before dark mode, commit 6bed22c).
GROUPS = {
	"science": ("Science", "#0E7490", "#CFFAFE", "#164E63"),        # cyan
	"mathematics": ("Mathematics", "#1E3A8A", "#DBEAFE", "#1E3A8A"),  # dark blue
	"technology": ("Technology", "#6D28D9", "#EDE9FE", "#4C1D95"),   # purple
	"arts": ("Arts", "#A16207", "#FEF9C3", "#713F12"),               # yellow
	"music": ("Music", "#C2410C", "#FFEDD5", "#7C2D12"),             # orange
	"humanities": ("Humanities", "#B91C1C", "#FEE2E2", "#7F1D1D"),   # red
	"society": ("Society", "#4B5563", "#F3F4F6", "#1F2937"),         # grey
	"practical": ("Practical", "#8A5A2B", "#F5E6D3", "#5C3A12"),     # tan
	"sport": ("Sport", "#166534", "#DCFCE7", "#14532D"),             # dark green
	"recreation": ("Recreation", "#4D7C0F", "#ECFCCB", "#365314"),   # bright green
}
FALLBACK_GROUP = ("Other", "#57534E", "#ECEAEE", "#3B3740")

# key: (dark bg, dark fg): 30% hue over the dark surface, and 70% white
DARK_PILLS = {
	"science": ("#183542", "#B7D5DE"),
	"mathematics": ("#1D2440", "#BCC4DC"),
	"technology": ("#341E58", "#D3BEF4"),
	"arts": ("#443019", "#E3D0B5"),
	"music": ("#4E261B", "#EDC6B6"),
	"humanities": ("#4B1B20", "#EABBBB"),
	"society": ("#2A2C35", "#C9CCD0"),
	"practical": ("#3D2D24", "#DCCEBF"),
	"sport": ("#1A3027", "#B9D1C2"),
	"recreation": ("#2B371C", "#CAD8B7"),
	"other": ("#2E2B2E", "#CDCBCA"),
}

# Other words that mean a category (exact match only), for search. Easy to extend:
# add lowercase words to a list. Used by the server (match_categories) and sent to
# the page with the palette. NOT YET AGREED with the team.
CATEGORY_ALIASES = {
	"science": ["sciences"],
	"mathematics": ["maths", "math"],
	"technology": ["tech"],
	"arts": ["art"],
	"music": [],
	"humanities": ["humanity"],
	"society": [],
	"practical": [],
	"sport": ["sports"],
	"recreation": [],
}

# backend category slug -> group key
CATEGORY_GROUP = {
	"science-and-the-natural-world": "science",
	"mathematics-and-logic": "mathematics",
	"technology-and-computing": "technology",
	"engineering-and-invention": "technology",
	"arts-and-creative-expression": "arts",
	"music-and-performing-arts": "music",
	"literature-and-language": "humanities",
	"history-and-civilisation": "humanities",
	"philosophy-and-intellectual-pursuits": "humanities",
	"religion-and-spirituality": "humanities",
	"politics-law-and-society": "society",
	"business-and-economics": "society",
	"geography-and-exploration": "society",
	"personal-development-and-lifestyle": "society",
	"food-and-culinary-arts": "practical",
	"collecting-and-craftsmanship": "practical",
	"transport-and-machinery": "practical",
	"sport-and-physical-activities": "sport",
	"nature-and-outdoor-recreation": "recreation",
	"games-and-recreation": "recreation",
}


def on_dark(hex_colour):
	"""
	A category hue lifted for the dark theme (45% hue, 55% white), used as --cat
	on the home page boxes. Deep hues like dark blue would vanish on the dark
	surface otherwise. Dots are >= 5.6 : 1 on the surface, and ink on its 24%
	tint is >= 9 : 1.
	"""
	h = hex_colour.lstrip("#")
	r, g, b = (round(int(h[i:i + 2], 16) * .45 + 255 * .55) for i in (0, 2, 4))
	return f"#{r:02X}{g:02X}{b:02X}"


def match_categories(query, names=None, aliases=None):
	"""
	Which categories a search query names, best first: [(group key, how)].
	how is "exact" (the name: "science"), "alias" (a word in CATEGORY_ALIASES:
	"maths") or "prefix" (the start of a name, 3+ characters: "mus"). Case and
	extra spaces are ignored. names/aliases default to GROUPS/CATEGORY_ALIASES.
	"""
	q = " ".join((query or "").lower().split())
	if not q:
		return []
	names = names or {key: group[0] for key, group in GROUPS.items()}
	aliases = CATEGORY_ALIASES if aliases is None else aliases
	found = {}
	for key, name in names.items():
		if name.lower() == q:
			found[key] = "exact"
	for key, words in aliases.items():
		if key not in found and q in [w.lower() for w in words]:
			found[key] = "alias"
	if len(q) >= 3:
		for key, name in names.items():
			if key not in found and name.lower().startswith(q):
				found[key] = "prefix"
	order = {"exact": 0, "alias": 1, "prefix": 2}
	return sorted(found.items(), key=lambda item: order[item[1]])


def category_slug(category_name):
	"""'Politics, law and society' -> 'politics-law-and-society'"""
	return re.sub(r"[^a-z0-9]+", "-", (category_name or "").lower()).strip("-")


def group_of(slug):
	"""Group key for a backend category slug, or None if it isn't mapped."""
	return CATEGORY_GROUP.get(slug or "")


def group_style(group_key):
	"""(name, strong, light bg, light fg) for a group key, or grey 'Other'."""
	return GROUPS.get(group_key or "", FALLBACK_GROUP)


def group_var(group_key, part=""):
	"""CSS variable for a group's colour: part "" (hue), "bg" or "fg". Follows the theme."""
	key = group_key if group_key in GROUPS else "other"
	return f"var(--cat-{key}{'-' + part if part else ''})"


def category_style(slug):
	"""(name, bg, fg) for a backend category slug: its group's pill colours, as CSS variables."""
	key = group_of(slug)
	return group_style(key)[0], group_var(key, "bg"), group_var(key, "fg")


def theme_css():
	"""
	The light and dark values of every category variable, for base.html:
	--cat-<key> (hue), --cat-<key>-bg and --cat-<key>-fg.
	"""
	light, dark = [], []
	for key, (_name, strong, bg, fg) in [*GROUPS.items(), ("other", FALLBACK_GROUP)]:
		dark_bg, dark_fg = DARK_PILLS[key]
		light.append(f"--cat-{key}: {strong}; --cat-{key}-bg: {bg}; --cat-{key}-fg: {fg};")
		dark.append(f"--cat-{key}: {on_dark(strong)}; --cat-{key}-bg: {dark_bg}; --cat-{key}-fg: {dark_fg};")
	return (
		":root, :root[data-theme=\"dark\"] { " + " ".join(dark) + " }\n"
		":root[data-theme=\"light\"] { " + " ".join(light) + " }"
	)


def palette_for_js():
	"""
	{"categories": {backend slug: group key}, "groups": {group key: {name, colour}}}
	so home.js groups and colours search results from this file. "other" is the
	grey fallback for untagged or unmapped interests.
	"""
	groups = {key: {"name": name, "colour": group_var(key)} for key, (name, *_colours) in GROUPS.items()}
	groups["other"] = {"name": FALLBACK_GROUP[0], "colour": group_var("other")}
	return {"categories": dict(CATEGORY_GROUP), "groups": groups}


# key: (label shown to people, colour). White icons have at least 4.5 : 1 on each.
AVATAR_COLOURS = {
	"palatinate": ("Palatinate", "#7E317B"),
	"blue": ("Blue", "#1F5FAD"),
	"green": ("Green", "#1E7A4C"),
	"teal": ("Teal", "#0F6E7A"),
	"indigo": ("Indigo", "#4B44A6"),
	"rose": ("Rose", "#A8295E"),
	"rust": ("Rust", "#9A3F12"),
	"slate": ("Slate", "#474552"),
}
AVATAR_DEFAULT = "palatinate"


def avatar_colour(key):
	"""Hex colour for an avatar key, or the default if the key is unknown."""
	return AVATAR_COLOURS.get(key, AVATAR_COLOURS[AVATAR_DEFAULT])[1]
