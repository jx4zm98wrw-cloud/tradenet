"""Classifier rules: VN surnames + company-suffix tokens/patterns."""

from __future__ import annotations

# Top Vietnamese surnames (covers ~98% of the VN population).
# First-word match against this set is the strongest signal that an applicant
# name is an individual rather than a company.
VN_SURNAMES = frozenset(
    {
        "Nguyễn",
        "Trần",
        "Lê",
        "Phạm",
        "Hoàng",
        "Huỳnh",
        "Phan",
        "Vũ",
        "Võ",
        "Đặng",
        "Bùi",
        "Đỗ",
        "Hồ",
        "Ngô",
        "Dương",
        "Lý",
        "Mai",
        "Đinh",
        "Lương",
        "Vương",
        "Tô",
        "Tăng",
        "Châu",
        "Trịnh",
        "Đoàn",
        "Cao",
        "Đào",
        "Lâm",
        "Lưu",
        "Quách",
        "Tống",
        "Hà",
        "Hứa",
        "Khúc",
        "Kiều",
        "La",
        "Mã",
        "Nông",
        "Tạ",
        "Thái",
        "Triệu",
        "Văn",
        "Vi",
        "Bạch",
        "Chu",
        "Đàm",
        "Lại",
        "Nghiêm",
        "Phùng",
        "Trương",
        "Uông",
        # Added after audits revealed Vietnamese names landing in Unknown:
        "Đồng",
        "Quảng",
        "An",
        "Tiêu",
        "Sỹ",
        "Khổng",
        "Tôn",
        "Quang",
        "Diếp",
        "Sử",
        "Lèo",
        "Quản",
        "Nhâm",
        "Phí",
        "Lường",
        "Vì",
        "Đậu",
        "Viên",
        "Từ",
        "Ngụy",
        "Công",
        "Âu",
    }
)
VN_SURNAMES_UPPER = frozenset(s.upper() for s in VN_SURNAMES)

# Unambiguous high-confidence company tokens. Match against any of these wins
# over VN-surname signal — handles edge cases like "NGUYỄN COMPANY LIMITED".
# Word-boundary matched, so short tokens (LTD, AG, SA) are safe.
STRONG_COMPANY_SUFFIXES = frozenset(
    {
        "ltd",
        "ltd.",
        "limited",
        "llc",
        "l.l.c.",
        "inc",
        "inc.",
        "incorporated",
        "corp",
        "corp.",
        "corporation",
        "company",
        "co.,ltd",
        "co., ltd",
        "gmbh",
        "mbh",
        "s.a.",
        "sàrl",
        "sarl",
        "plc",
        "pty",
        "công ty",
        "tổng công ty",
        "doanh nghiệp",
        "tập đoàn",
        "xí nghiệp",
        "công ty cổ phần",
        "công ty tnhh",
        "công ty hợp danh",
        "tnhh",
        "trung tâm nghiên cứu",
        "viện",
        "ag",
        "ab",
        "spa",
        "srl",
        "b.v.",
        "n.v.",
        "kk",
        "k.k.",
        "oy",
        "aps",
        "anonim şirketi",
        "anonim sirketi",
    }
)
# Typo-tolerant prefix stems — match the canonical stem plus any letters so
# misspellings ("CORPORTION", "INCORPORATION") and foreign-language variants
# ("INDUSTRIJA") still classify as Company. Each is bounded so partial matches
# inside other words (e.g. "INCORPOREAL"-style) don't fire — the boundary
# requires non-word char before/after.
TYPO_TOLERANT_COMPANY_PATTERNS = (
    "corp[a-z]*",  # corp, corps, corporate, corporation, corportion
    "incorp[a-z]*",  # incorp, incorporated, incorporation
    "limit[a-z]*",  # limited, limitee (rare typo)
    "compan[a-z]*",  # company, companies, compnay (typo)
    "industri[a-z]*",  # industries, industrial, industrija (Croatian)
    "manufactur[a-z]*",  # manufacturing, manufacture
    "enterpr[a-z]*",  # enterprise, enterprises
    "holdin[a-z]*",  # holdings, holding
)
