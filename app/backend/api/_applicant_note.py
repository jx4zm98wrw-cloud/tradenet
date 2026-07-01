"""Strip IP VIETNAM internal processing-notes prepended to an applicant name.

IP VIETNAM's registry frequently glues an operational note onto the FRONT of the
applicant field — a delivery instruction, a third-party-opinion flag, or a
correspondence-merge marker — e.g.::

    "(Nhận GCN tại Cục - 0948 456 705)Công ty cổ phần Tập đoàn VGREEN"
    "(gửi VB VP 2)ABC Co."
    "(có ý kiến người thứ 3)Nguyễn Văn A"

These notes are not part of the entity's name. They leak into every surface that
shows the applicant (mark header, search cards, the domestic-record panel) and —
worse — they fragment entity canonicalization, so the SAME company groups under
two different `applicant_norm` keys.

`strip_registry_note` removes such a note ONLY when it is a LEADING parenthetical
whose content matches the registry-note vocabulary below. This is deliberately
narrow: a leading parenthetical that is NOT a known note (e.g. a legitimate
"(INC)" suffix or an ISO country code) is left untouched, and notes that appear
mid/tail (which may be legitimate clarifiers) are never stripped.

Pure stdlib (`re` only) so the ingest worker, the domestic-enrichment parser, and
the entity-canonicalization derivation can all share one implementation.
"""

from __future__ import annotations

import re

# A leading parenthetical and its inner content: "(...)". Trailing whitespace is
# consumed so "(note) Foo" and "(note)Foo" both reduce to "Foo".
_LEADING_PAREN = re.compile(r"^\s*\(([^)]*)\)\s*")

# Vocabulary that marks a parenthetical as an IP VIETNAM processing note rather
# than part of a name. Case-insensitive; Vietnamese diacritics as they appear in
# the registry. The trailing digit-run catches the phone numbers the delivery
# notes carry (e.g. "0948 456 705") even if the wording varies.
_NOTE_VOCAB = re.compile(
    r"(?i)("
    r"nhận|gửi|"  # receive / send (delivery instructions)
    r"gcn|vbbh|\bvb\b|"  # certificate / protection title / document
    r"đ/\s*c|"  # địa chỉ (address) abbreviation "đ/c"
    r"tại\s+cục|cục\s*-|\bvp\s*\d|"  # at the Office / at office 2 (VP2)
    r"ý\s*kiến|người\s+thứ|"  # third-party-opinion flags
    r"ghép|giục|loại\s+trừ|"  # merge-correspondence / urge-issuance / exclusion
    r"\d{3,}"  # embedded numeric code / phone number
    r")"
)


def strip_registry_note(name: str | None) -> str | None:
    """Remove leading IP VIETNAM processing-note parenthetical(s) from `name`.

    Repeats while the string still starts with a note-matching parenthetical (a
    few records carry two). Returns the trimmed remainder, or the ORIGINAL value
    unchanged when there is no leading note — and never returns an empty string
    (if stripping would erase everything, the original is kept, defensively).
    """
    if not name:
        return name
    s = name
    while True:
        m = _LEADING_PAREN.match(s)
        if not m or not _NOTE_VOCAB.search(m.group(1)):
            break
        s = s[m.end() :]
    s = s.strip()
    return s or name
