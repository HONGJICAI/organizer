"""Find likely-duplicate comics by filename.

Comic filenames are usually a title buried in tags — scanlation group, author,
event, edition: ``(C99) [Circle (Author)] Title (Series) [中国翻訳] [DL版].zip``.
Two copies of the same work rarely share those tags, so names are first reduced
to a *core title* (tags, extension, punctuation and width differences removed)
plus a *volume signature* (every number left in the title). Items with the same
core and signature are exact duplicates; cores that are merely close (same
signature, SequenceMatcher ratio above a threshold) are grouped as similar.

The volume signature is the guard against the classic false positive: ``Title
01`` and ``Title 02`` share a core but are different books, never duplicates.
"""
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Sequence, Tuple

ARCHIVE_EXTENSIONS = {".zip", ".rar", ".cbz", ".cbr", ".7z", ".pdf"}

# Bracketed tags. NFKC has already folded full-width （）［］ to ASCII.
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】|\{[^}]*\}|〔[^〕]*〕")

_CN_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
# 第三卷 / 第十二話 style volume markers with Chinese numerals.
_VOLUME_SUFFIX = "[卷巻话話集册冊部章回篇]"
_CN_VOLUME = re.compile(rf"第([零〇一二两三四五六七八九十百]+){_VOLUME_SUFFIX}")
# Volume markers around arabic numbers (vol.3, #3, 第3话, 3卷) — the marker
# words go so "Title Vol.3" and "Title 第3卷" reduce to the same core.
_VOLUME_MARKER = re.compile(
    rf"(?:\bvol(?:ume)?|\bch(?:apter)?|\bep|#|第)\.?\s*(\d+)\s*{_VOLUME_SUFFIX}?"
    rf"|(\d+)\s*{_VOLUME_SUFFIX}"
)
# 上/中/下 and 前/後 halves are volumes too; map them onto the number line.
# A bare trailing 上/下 only counts after a space, so 天下 stays a word.
_HALVES = re.compile(
    r"([前后後])[编編篇]|([上中下])[卷巻册冊编編篇]|(?<=\s)([上中下])(?=\s*$)"
)
_HALF_VALUES = {"前": 1, "上": 1, "中": 2, "后": 3, "後": 3, "下": 3}
_NUMBER = re.compile(r"\d+")
# \w is Unicode-aware, so CJK/kana survive; only separators and symbols go.
_NON_WORD = re.compile(r"[\W_]+")


def _cn_to_int(text: str) -> int:
    total, current = 0, 0
    for ch in text:
        if ch == "百":
            total += (current or 1) * 100
            current = 0
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        else:
            current = _CN_DIGITS[ch]
    return total + current


def _strip_extension(name: str) -> str:
    dot = name.rfind(".")
    if dot > 0 and name[dot:].lower() in ARCHIVE_EXTENSIONS:
        return name[:dot]
    return name


def normalize(name: str) -> Tuple[str, Tuple[int, ...]]:
    """Reduce a filename to ``(core title, volume signature)``."""
    text = unicodedata.normalize("NFKC", _strip_extension(name)).lower()
    stripped = _BRACKETS.sub(" ", text)
    # A name that is nothing but tags (``[Author] [Title]``) would reduce to
    # nothing; fall back to keeping the bracket contents.
    if not _NON_WORD.sub("", stripped):
        stripped = re.sub(r"[\[\](){}【】〔〕]", " ", text)
    stripped = _CN_VOLUME.sub(lambda m: f" {_cn_to_int(m.group(1))} ", stripped)
    stripped = _HALVES.sub(
        lambda m: f" {_HALF_VALUES[next(g for g in m.groups() if g)]} ", stripped
    )
    stripped = _VOLUME_MARKER.sub(lambda m: f" {m.group(1) or m.group(2)} ", stripped)
    numbers = tuple(int(n) for n in _NUMBER.findall(stripped))
    core = _NON_WORD.sub("", _NUMBER.sub(" ", stripped))
    return core, numbers


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def is_similar(a: str, b: str, threshold: float) -> bool:
    m = SequenceMatcher(None, a, b, autojunk=False)
    # The quick ratios are cheap upper bounds on ratio(); most pairs fail them.
    return (
        m.real_quick_ratio() >= threshold
        and m.quick_ratio() >= threshold
        and m.ratio() >= threshold
    )


def _candidate_pairs(cores: Sequence[str]) -> Iterable[Tuple[int, int]]:
    # Comparing every pair is O(n²) SequenceMatcher calls — too slow for a big
    # library. Real duplicates almost always keep either the start or the end
    # of the title intact (tags get added around it, a subtitle gets dropped),
    # so only compare titles that share their first or last two characters.
    buckets = defaultdict(list)
    for i, core in enumerate(cores):
        if len(core) < 2:
            continue
        buckets["^" + core[:2]].append(i)
        buckets["$" + core[-2:]].append(i)
    seen = set()
    for members in buckets.values():
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                pair = (members[x], members[y])
                if pair not in seen:
                    seen.add(pair)
                    yield pair


def find_groups(names: Sequence[str], threshold: float = 0.85) -> List[Tuple[List[int], bool]]:
    """Group indices of ``names`` that look like the same work.

    Returns ``(indices, exact)`` per group of two or more, where ``exact`` means
    every member normalized to the same key. Groups and their members keep
    input order.
    """
    keys = [normalize(n) for n in names]
    # Collapse identical keys first so the fuzzy pass compares each distinct
    # title once, not once per copy.
    distinct: dict = {}
    for i, key in enumerate(keys):
        distinct.setdefault(key, []).append(i)
    key_list = list(distinct)
    uf = _UnionFind(len(key_list))

    by_volume = defaultdict(list)
    for k, (core, numbers) in enumerate(key_list):
        if core:
            by_volume[numbers].append(k)
    for members in by_volume.values():
        cores = [key_list[k][0] for k in members]
        for x, y in _candidate_pairs(cores):
            if is_similar(cores[x], cores[y], threshold):
                uf.union(members[x], members[y])

    clusters: dict = defaultdict(list)
    for k in range(len(key_list)):
        clusters[uf.find(k)].append(k)
    groups = []
    for ks in clusters.values():
        indices = sorted(i for k in ks for i in distinct[key_list[k]])
        # An empty core (e.g. a name that is just "001") says nothing about the
        # work; don't group those on number alone.
        if len(indices) < 2 or not key_list[ks[0]][0]:
            continue
        groups.append((indices, len(ks) == 1))
    groups.sort(key=lambda g: g[0][0])
    return groups


def pick_keep(items: Sequence) -> Optional[int]:
    """Suggest which copy to keep: favorited first, then most pages, then largest."""
    if not items:
        return None
    best = max(items, key=lambda c: (bool(c.favorited), c.page or 0, c.size or 0))
    return best.id
