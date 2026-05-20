"""Rebuild cities_by_country.json from GeoNames cities500.

For each populated place (feature_class='P'), emit name + asciiname (and for VN,
any alternatename containing Vietnamese diacritics). Skip 1-3-char tokens and
all-caps-no-lowercase strings (airport/state codes that pollute matches).
"""
import json, re, sys, unicodedata
from collections import defaultdict
from pathlib import Path

SRC = Path("geonames_tmp/cities500.txt")
DST = Path("cities_by_country.json")

VN_DIACRITICS = re.compile(r'[ĂÂĐÊÔƠƯăâđêôơưḀ-ỿ]')
# VN admin prefixes that mark city-level entries — strip and keep the bare name.
VN_STRIP_PREFIX = re.compile(
    r'^(?:Thành\s+phố|TP\.?|T\.?P\.?|Tỉnh|Thị\s+xã|Thị\s+trấn)\s+',
    re.IGNORECASE,
)
# VN admin prefixes that mark sub-city units (districts/wards/communes) — drop entirely.
VN_DROP_PREFIX = re.compile(r'^(?:Quận|Huyện|Phường|Xã)\s+', re.IGNORECASE)

def is_latin_script(s: str) -> bool:
    for c in s:
        if c.isalpha() and not unicodedata.name(c, "").startswith("LATIN"):
            return False
    return True

def is_good_name(s: str, pop: int = 0) -> bool:
    if not s: return False
    # 3-char names tend to false-positive (Cam, Hyde, Bath) — allow only if population
    # is large enough that the entry is unambiguously a real, well-known city.
    min_len = 3 if pop >= 30000 else 4
    if len(s) < min_len: return False
    if len(s) > 60: return False
    if not is_latin_script(s): return False
    if not any(c.islower() for c in s): return False  # all-caps → codes (HAN, NSW, VIC…)
    if any(ch in s for ch in "(){}[]/\\|"): return False
    return True

def is_canonical_alt(s: str, pop: int = 0) -> bool:
    """Stricter than is_good_name — for sucking alternatenames into the bucket.
    Bias toward short proper-noun forms that look like real address tokens.
    """
    # Alternatenames don't get the 3-char relaxation; "Syd"/"Vin" abbreviations are
    # too false-positive prone in foreign-language address text.
    if len(s) < 4: return False
    if not is_good_name(s, pop): return False
    if len(s) > 30: return False
    # Must look like Title Case: every alphabetic token starts with uppercase or is a tiny
    # connector word ("on", "of", "le", "la", "der"). Excludes "ho chi minh shi" lowercase
    # romanizations, but keeps "Le Grand-Saconnex", "New York", "Sài Gòn".
    tokens = [t for t in re.split(r'[\s\-]+', s) if t]
    if not tokens: return False
    for t in tokens:
        if t[0].isalpha() and t[0].islower() and t.lower() not in {"of","on","de","la","le","les","da","do","du","der","von","van","upon","an","am"}:
            return False
    return True

def normalize_vn(s: str) -> str:
    # GeoNames sometimes stores Vietnamese D-with-stroke as 'Ð' (U+00D0, Eth) instead
    # of the canonical 'Đ' (U+0110). Map it so "Ðà Lạt" becomes "Đà Lạt".
    return s.replace("Ð", "Đ").replace("ð", "đ")

cities = defaultdict(set)
total = kept = 0
with SRC.open(encoding="utf-8") as f:
    for line in f:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 19: continue
        total += 1
        name, asciiname, alts, cc = parts[1], parts[2], parts[3], parts[8]
        try:
            pop = int(parts[14]) if parts[14] else 0
        except ValueError:
            pop = 0
        if not cc or len(cc) != 2: continue
        if cc == "VN":
            name = normalize_vn(name)
        bucket = cities[cc]
        added_here = 0
        if cc == "VN" and VN_DROP_PREFIX.match(name):
            continue
        name_to_add = VN_STRIP_PREFIX.sub("", name).strip() if cc == "VN" else name
        if is_good_name(name_to_add, pop):
            bucket.add(name_to_add); added_here += 1
        if asciiname != name and is_good_name(asciiname, pop):
            bucket.add(asciiname); added_here += 1
        for alt in alts.split(","):
            alt = alt.strip()
            if cc == "VN":
                alt = normalize_vn(alt)
                if VN_DROP_PREFIX.match(alt): continue
                stripped = VN_STRIP_PREFIX.sub("", alt).strip()
                candidate = stripped if stripped != alt else alt
            else:
                candidate = alt
            if is_canonical_alt(candidate, pop):
                bucket.add(candidate); added_here += 1
        if added_here:
            kept += 1

# Gazette tags HK and Macao applicants with country code (CN). Surface those cities
# from the CN bucket so the matcher doesn't draw blanks on HK/MO addresses.
for source_cc in ("HK", "MO"):
    cities["CN"].update(cities.get(source_cc, set()))

# Apply manual overrides (additions/removals layered on top of GeoNames data).
OVERRIDES = Path("cities_overrides.json")
override_summary = ""
if OVERRIDES.exists():
    raw = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    added = removed = 0
    for cc, items in (raw.get("add") or {}).items():
        cities.setdefault(cc, set()).update(items); added += len(items)
    for cc, items in (raw.get("remove") or {}).items():
        if cc in cities:
            before = len(cities[cc])
            cities[cc].difference_update(items)
            removed += before - len(cities[cc])
    override_summary = f"Overrides: +{added} added, -{removed} removed (from {OVERRIDES})"

out = {cc: sorted(v) for cc, v in cities.items()}
DST.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"Source rows:      {total}")
print(f"Cities kept:      {kept}")
print(f"Countries:        {len(out)}")
print(f"Total city names: {sum(len(v) for v in out.values())}")
for cc in ("VN","CN","JP","KR","AU","GB","US","DE","FR","CH"):
    print(f"  {cc}: {len(out.get(cc, []))}")
if override_summary:
    print(override_summary)
print(f"Output: {DST} ({DST.stat().st_size:,} bytes)")
