"""
clean_lca.py - cleaning pipeline for DOL OFLC LCA disclosure files.

Turns one raw LCA quarterly file (Excel, ~100 columns, ~440k rows) into a tidy
table of data / ML / analytics roles that can be loaded into PostgreSQL and
Power BI.

Every step is a small function so it can be run and checked one at a time in
notebooks/01_clean_lca.ipynb, or all at once with `run_pipeline()`.

Source: U.S. Department of Labor, Office of Foreign Labor Certification,
LCA Programs (H-1B, H-1B1, E-3) disclosure data. An LCA is a filing by an
employer, not an H-1B approval; counts here are LCA filings.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Loading
# ---------------------------------------------------------------------------

# Column names change slightly between DOL releases. Map old/alternate names
# to the name used in the FY2026 files.
COLUMN_RENAMES = {
    "H-1B_DEPENDENT": "H_1B_DEPENDENT",
}

# Columns kept for analysis. Point-of-contact, attorney and preparer names,
# emails and phone numbers are dropped on purpose: they are not needed and
# this repo is public.
KEEP_COLUMNS = [
    "CASE_NUMBER",
    "CASE_STATUS",
    "RECEIVED_DATE",
    "DECISION_DATE",
    "VISA_CLASS",
    "JOB_TITLE",
    "SOC_CODE",
    "SOC_TITLE",
    "FULL_TIME_POSITION",
    "BEGIN_DATE",
    "END_DATE",
    "TOTAL_WORKER_POSITIONS",
    "NEW_EMPLOYMENT",
    "CONTINUED_EMPLOYMENT",
    "CHANGE_EMPLOYER",
    "EMPLOYER_NAME",
    "TRADE_NAME_DBA",
    "EMPLOYER_CITY",
    "EMPLOYER_STATE",
    "EMPLOYER_FEIN",
    "NAICS_CODE",
    "WORKSITE_CITY",
    "WORKSITE_COUNTY",
    "WORKSITE_STATE",
    "WORKSITE_POSTAL_CODE",
    "WAGE_RATE_OF_PAY_FROM",
    "WAGE_RATE_OF_PAY_TO",
    "WAGE_UNIT_OF_PAY",
    "PREVAILING_WAGE",
    "PW_UNIT_OF_PAY",
    "PW_WAGE_LEVEL",
    "H_1B_DEPENDENT",
    "WILLFUL_VIOLATOR",
]

_FILE_FY_Q = re.compile(r"FY(\d{4})_Q(\d)", re.IGNORECASE)


def parse_file_period(path: str | Path) -> tuple[int | None, int | None]:
    """Read fiscal year and quarter from a DOL file name, e.g.
    'LCA_Disclosure_Data_FY2026_Q3.xlsx' -> (2026, 3)."""
    m = _FILE_FY_Q.search(Path(path).name)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def load_quarter(
    xlsx_path: str | Path,
    cache_dir: str | Path | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Load one raw DOL LCA Excel file as all-text columns.

    The first read uses the fast Rust 'calamine' Excel engine (several minutes
    for a 240 MB file) and saves a Parquet copy. Later reads use the Parquet
    copy (seconds). Pass refresh=True to re-read the Excel file.

    Everything is read as text (dtype=str) so nothing is silently converted;
    types are set explicitly in later steps.
    """
    xlsx_path = Path(xlsx_path)
    cache_dir = Path(cache_dir) if cache_dir else xlsx_path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / (xlsx_path.stem + ".parquet")

    if cache_path.exists() and not refresh:
        df = pd.read_parquet(cache_path)
    else:
        df = pd.read_excel(xlsx_path, engine="calamine", dtype=str, sheet_name=0)
        df.to_parquet(cache_path, index=False)

    fy, q = parse_file_period(xlsx_path)
    df.attrs["source_file"] = xlsx_path.name
    df.attrs["source_fy"] = fy
    df.attrs["source_quarter"] = q
    return df


def select_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename known alternate column names and keep only KEEP_COLUMNS.
    Missing columns (possible in older files) are added as empty."""
    out = df.rename(columns=COLUMN_RENAMES)
    missing = [c for c in KEEP_COLUMNS if c not in out.columns]
    for c in missing:
        out[c] = pd.NA
    out = out[KEEP_COLUMNS].copy()
    out.attrs = dict(df.attrs)
    out.attrs["missing_columns"] = missing
    # Trim whitespace in every text column; turn empty strings into NA.
    for c in out.columns:
        out[c] = out[c].astype("string").str.strip().replace("", pd.NA)
    return out


# ---------------------------------------------------------------------------
# 2. Status, visa and dates
# ---------------------------------------------------------------------------


def _fiscal_year(d: pd.Series) -> pd.Series:
    """U.S. federal fiscal year: Oct 1 - Sep 30. Oct 2025 -> FY2026."""
    return (d.dt.year + (d.dt.month >= 10).astype("Int64")).astype("Int64")


def _fiscal_quarter(d: pd.Series) -> pd.Series:
    """Q1 = Oct-Dec, Q2 = Jan-Mar, Q3 = Apr-Jun, Q4 = Jul-Sep."""
    return (((d.dt.month - 10) % 12) // 3 + 1).astype("Int64")


def add_status_and_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Parse dates, add fiscal year/quarter of the DOL decision, and flag
    certified H-1B filings."""
    out = df.copy()
    for c in ["RECEIVED_DATE", "DECISION_DATE", "BEGIN_DATE", "END_DATE"]:
        out[c] = pd.to_datetime(out[c], errors="coerce")

    out["decision_fy"] = _fiscal_year(out["DECISION_DATE"])
    out["decision_fq"] = _fiscal_quarter(out["DECISION_DATE"])
    out["source_file"] = df.attrs.get("source_file")
    out["source_fy"] = df.attrs.get("source_fy")
    out["source_quarter"] = df.attrs.get("source_quarter")

    # Normalise "Certified - Withdrawn" / "Certified-Withdrawn" spellings.
    status = out["CASE_STATUS"].str.replace(r"\s*-\s*", " - ", regex=True)
    out["CASE_STATUS"] = status
    out["is_h1b"] = out["VISA_CLASS"].eq("H-1B").fillna(False)
    out["is_certified"] = status.eq("Certified").fillna(False)
    out["is_certified_h1b"] = out["is_h1b"] & out["is_certified"]

    out["TOTAL_WORKER_POSITIONS"] = pd.to_numeric(
        out["TOTAL_WORKER_POSITIONS"], errors="coerce"
    ).astype("Int64")
    out.attrs = dict(df.attrs)
    return out


# ---------------------------------------------------------------------------
# 3. SOC codes
# ---------------------------------------------------------------------------

# Accepts '15-2051.01', '15-2051', '15-1212 .00', '17-2199-05',
# '15-1252.00 - Software Developers', '17-2144.0'. A dash between the 2- and
# 4-digit parts is required so NAICS-like values ('541618') are rejected.
_SOC_RE = re.compile(r"^\s*(\d{2})\s*-\s*(\d{4})(?:\s*[.\-]\s*(\d{1,2})(?!\d))?")


def normalize_soc(df: pd.DataFrame) -> pd.DataFrame:
    """Add soc_6 ('15-2051') and soc_8 ('15-2051.01'). Codes without a
    detail suffix get '.00'. Unparseable codes become NA and soc_valid=False."""
    out = df.copy()
    parts = out["SOC_CODE"].str.extract(_SOC_RE)
    major = parts[0] + "-" + parts[1]
    detail = parts[2].fillna("00").str.ljust(2, "0")
    out["soc_6"] = major
    out["soc_8"] = (major + "." + detail).where(major.notna())
    out["soc_valid"] = major.notna()
    out.attrs = dict(df.attrs)
    return out


# ---------------------------------------------------------------------------
# 4. Wages
# ---------------------------------------------------------------------------

# Hours-per-year convention used by DOL OFLC (40 h x 52 weeks).
ANNUAL_FACTOR = {
    "Year": 1,
    "Hour": 2080,
    "Week": 52,
    "Bi-Weekly": 26,
    "Month": 12,
}

# Annual wages outside this range are kept but flagged for review.
WAGE_MIN_PLAUSIBLE = 20_000
WAGE_MAX_PLAUSIBLE = 1_000_000
# A non-yearly rate at or above this is treated as a yearly salary typo.
UNIT_TYPO_THRESHOLD = 15_000


def _to_number(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype("string").str.replace(r"[$,\s]", "", regex=True), errors="coerce"
    )


def annualize_wages(df: pd.DataFrame) -> pd.DataFrame:
    """Convert offered wage (from/to) and prevailing wage to annual dollars.

    wage_annual_from is the lower end of the offered range and is the main
    wage used in the dashboard. wage_annual_to is filled only when the filing
    gives a range. wage_flag marks values to check instead of deleting them.
    """
    out = df.copy()
    f_wage = out["WAGE_UNIT_OF_PAY"].map(ANNUAL_FACTOR)
    f_pw = out["PW_UNIT_OF_PAY"].map(ANNUAL_FACTOR)

    w_from = _to_number(out["WAGE_RATE_OF_PAY_FROM"])
    w_to = _to_number(out["WAGE_RATE_OF_PAY_TO"])
    pw = _to_number(out["PREVAILING_WAGE"])

    # Unit typos: e.g. 130000 filed as "Week" or 85000 as "Hour". A non-yearly
    # rate of 15,000 or more is almost certainly an annual salary, so it is
    # treated as yearly and flagged (raw values stay in the WAGE_* columns).
    wage_unit_fix = out["WAGE_UNIT_OF_PAY"].ne("Year").fillna(False) & (w_from >= UNIT_TYPO_THRESHOLD).fillna(False)
    pw_unit_fix = out["PW_UNIT_OF_PAY"].ne("Year").fillna(False) & (pw >= UNIT_TYPO_THRESHOLD).fillna(False)
    f_wage = f_wage.where(~wage_unit_fix, 1)
    f_pw = f_pw.where(~pw_unit_fix, 1)

    out["wage_annual_from"] = (w_from * f_wage).round(0)
    out["wage_annual_to"] = (w_to * f_wage).round(0)
    out["pw_annual"] = (pw * f_pw).round(0)
    # A "to" value of 0 or below "from" is treated as "no range given".
    bad_to = out["wage_annual_to"].le(0) | (out["wage_annual_to"] < out["wage_annual_from"])
    out.loc[bad_to.fillna(False), "wage_annual_to"] = np.nan
    out["wage_vs_pw_pct"] = (
        (out["wage_annual_from"] / out["pw_annual"] - 1) * 100
    ).round(1).where(out["pw_annual"] > 0)

    w = out["wage_annual_from"]
    flag = pd.Series("ok", index=out.index, dtype="string")
    flag[f_wage.isna()] = "unknown_unit"
    flag[w.isna() & f_wage.notna()] = "missing"
    flag[w < WAGE_MIN_PLAUSIBLE] = "below_20k"
    flag[w > WAGE_MAX_PLAUSIBLE] = "above_1m"
    flag[wage_unit_fix & flag.eq("ok")] = "unit_assumed_year"
    out["wage_flag"] = flag

    out["PW_WAGE_LEVEL"] = out["PW_WAGE_LEVEL"].fillna("Not reported")
    out.attrs = dict(df.attrs)
    return out


# ---------------------------------------------------------------------------
# 5. Employer names
# ---------------------------------------------------------------------------

# Legal-form words removed from the END of a name (repeatedly), so
# "GOOGLE LLC" and "Google, L.L.C." both become "GOOGLE".
_SUFFIXES = [
    "INCORPORATED", "INC", "LLC", "L L C", "LLP", "L L P", "LP", "L P",
    "PLLC", "PLC", "PC", "P C", "PA", "P A", "CORPORATION", "CORP",
    "COMPANY", "CO", "LIMITED", "LTD", "NA", "N A", "GMBH", "AG", "SA",
    "SE", "BV", "NV", "PTE", "PVT",
    "AND",  # left over from '& Co.' -> 'AND CO' once CO is removed
]
_SUFFIX_RE = re.compile(
    r"(?:\s+(?:" + "|".join(sorted({re.escape(s) for s in _SUFFIXES}, key=len, reverse=True)) + r"))+\s*$"
)
_FEIN_RE = re.compile(r"^\d{2}-\d{7}$")


def clean_employer_name(s: pd.Series) -> pd.Series:
    """Uppercase, '&' -> 'AND', drop punctuation, collapse spaces, drop a
    leading 'THE' and trailing legal-form words (INC, LLC, CORP ...)."""
    x = s.astype("string").str.upper()
    x = x.str.replace("&", " AND ", regex=False)
    x = x.str.replace(r"[^\w\s]", " ", regex=True)  # punctuation -> space
    x = x.str.replace(r"_", " ", regex=False)
    x = x.str.replace(r"\s+", " ", regex=True).str.strip()
    x = x.str.replace(r"^THE\s+", "", regex=True)
    x = x.str.replace(_SUFFIX_RE, "", regex=True).str.strip()
    return x.replace("", pd.NA)


def standardize_employers(df: pd.DataFrame) -> pd.DataFrame:
    """Add employer_name_clean and employer_name_std.

    employer_name_clean: rule-based clean of the name as filed.
    employer_name_std:   one name per FEIN (the most common clean name filed
                         under that FEIN), so spelling variants of the same
                         legal entity are grouped. Rows with a missing or
                         malformed FEIN keep their clean name.

    Note: FEIN identifies a legal entity, not a brand. 'Amazon.com Services'
    and 'Amazon Web Services' have different FEINs and stay separate.
    """
    out = df.copy()
    out["employer_name_clean"] = clean_employer_name(out["EMPLOYER_NAME"])
    fein = out["EMPLOYER_FEIN"].astype("string").str.strip()
    valid = fein.str.match(_FEIN_RE).fillna(False) & ~fein.isin(["00-0000000"]).fillna(False)
    out["fein_valid"] = valid
    out["EMPLOYER_FEIN"] = fein

    tmp = out.loc[valid, ["EMPLOYER_FEIN", "employer_name_clean"]].dropna()
    # most common clean name per FEIN; ties broken alphabetically for stability
    counts = (
        tmp.groupby(["EMPLOYER_FEIN", "employer_name_clean"], observed=True)
        .size()
        .reset_index(name="n")
        .sort_values(["EMPLOYER_FEIN", "n", "employer_name_clean"], ascending=[True, False, True])
    )
    fein_name = counts.drop_duplicates("EMPLOYER_FEIN").set_index("EMPLOYER_FEIN")["employer_name_clean"]
    std = out["EMPLOYER_FEIN"].map(fein_name)
    out["employer_name_std"] = std.where(valid).fillna(out["employer_name_clean"]).astype("string")
    out.attrs = dict(df.attrs)
    return out


# ---------------------------------------------------------------------------
# 6. Job titles
# ---------------------------------------------------------------------------

# Abbreviation expansions, applied in order to the upper-cased title after
# punctuation is turned into spaces. Each pattern is a whole-word regex, so
# 'SR' never touches 'SRE'. Order matters: multi-word and context rules
# (e.g. BUS DEV, BUSINESS INTEL) come before the single-word ones.
TITLE_ABBREVIATIONS: list[tuple[str, str]] = [
    # multi-word / context-dependent first
    (r"\bBUS(?:INESS)? INTEL(?:L|LIG)?\b", "BUSINESS INTELLIGENCE"),
    (r"\bBUS(?:INESS)? INT\b", "BUSINESS INTELLIGENCE"),
    (r"\bBUS(?:INESS)? INTE\b", "BUSINESS INTELLIGENCE"),
    (r"\b(BUS(?:INESS)?|CORP(?:ORATE)?) DEV\b", r"\1 DEVELOPMENT"),
    (r"\bPLAN / DEV\b", "PLAN / DEVELOPMENT"),
    (r"\bDEV ?OPS\b", "DEVOPS"),
    (r"\b(ML|AI|MACHINE LEARNING) OPS\b", "MLOPS"),
    (r"\bOPS RESEARCH\b", "OPERATIONS RESEARCH"),
    (r"\bOPERATION RESEARCH\b", "OPERATIONS RESEARCH"),
    (r"\bDATA SCI\b", "DATA SCIENCE"),
    (r"\bADV(?:ANCE)? ANAL(?:Y|YTICS)?\b", "ADVANCED ANALYTICS"),
    (r"\bA I\b", "AI"),
    (r"\bM L\b", "ML"),
    # seniority
    (r"\bSR\b", "SENIOR"),
    (r"\bSNR\b", "SENIOR"),
    (r"\bJR\b", "JUNIOR"),
    (r"\bLD\b", "LEAD"),
    (r"\bPRINC?\b", "PRINCIPAL"),
    (r"\bASST\b", "ASSISTANT"),
    (r"\bASSOC\b", "ASSOCIATE"),
    (r"\bAVP\b", "ASSISTANT VICE PRESIDENT"),
    (r"\bSVP\b", "SENIOR VICE PRESIDENT"),
    (r"\bVP\b", "VICE PRESIDENT"),
    (r"\bDIR\b", "DIRECTOR"),
    # job nouns
    (r"\bMN?GR\b", "MANAGER"),
    (r"\bMNGR\b", "MANAGER"),
    (r"\bMGMT\b", "MANAGEMENT"),
    (r"\bMGT\b", "MANAGEMENT"),
    (r"\b(?:ENGR|ENGG|ENGNR|ENG)\b", "ENGINEER"),
    (r"\b(?:ANLST|ANALY|ANAL)\b", "ANALYST"),
    (r"\b(?:SCI|SCNTST)\b", "SCIENTIST"),
    (r"\b(?:DEV|DVLPR)\b", "DEVELOPER"),
    (r"\bSPEC\b", "SPECIALIST"),
    (r"\bARCH\b", "ARCHITECT"),
    (r"\bCONSULT\b", "CONSULTANT"),
    (r"\bSTATS\b", "STATISTICS"),
    (r"\bBUS\b", "BUSINESS"),
    (r"\bINFO\b", "INFORMATION"),
    (r"\bSYS\b", "SYSTEMS"),
    (r"\bPROG\b", "PROGRAM"),
    (r"\bSOLNS?\b", "SOLUTIONS"),
    (r"\bMKTG\b", "MARKETING"),
    (r"\bADV\b", "ADVANCED"),
]
_TITLE_ABBREV = TITLE_ABBREVIATIONS  # backward-compatible alias

# Seniority / level words stripped to build job_title_base.
_LEVEL_RE = re.compile(
    r"\b(SENIOR|JUNIOR|LEAD|PRINCIPAL|STAFF|ASSOCIATE|ENTRY LEVEL|"
    r"I{1,3}|IV|V|VI|[0-9]+|L[0-9]+)\b"
)


def normalize_titles(df: pd.DataFrame) -> pd.DataFrame:
    """Add job_title_clean (uppercase, punctuation to spaces, common
    abbreviations expanded) and job_title_base (seniority and level numbers
    removed, used to group titles like 'Senior Data Scientist II' with
    'Data Scientist')."""
    out = df.copy()
    t = out["JOB_TITLE"].astype("string").str.upper()
    t = t.str.replace("&", " AND ", regex=False)
    t = t.str.replace(r"[^\w\s/+]", " ", regex=True)  # keep '/' (AI/ML) and '+'
    t = t.str.replace("/", " / ", regex=False)
    t = t.str.replace(r"\s+", " ", regex=True).str.strip()
    for pat, rep in TITLE_ABBREVIATIONS:
        t = t.str.replace(pat, rep, regex=True)
    t = t.str.replace(r"\s+", " ", regex=True).str.strip()
    out["job_title_clean"] = t

    b = t.str.replace(r"\(.*?\)", " ", regex=True)
    b = b.str.replace(_LEVEL_RE, " ", regex=True)
    b = b.str.replace(r"[/,]", " ", regex=True)
    b = b.str.replace(r"\s+", " ", regex=True).str.strip()
    out["job_title_base"] = b.replace("", pd.NA).fillna(t)
    out.attrs = dict(df.attrs)
    return out


# ---------------------------------------------------------------------------
# 7. Role family
# ---------------------------------------------------------------------------

ROLE_FAMILIES = [
    "Data Scientist",
    "ML/AI Engineer",
    "Data Engineer",
    "Statistician/Quant",
    "Data Analyst/BI",
]
OTHER = "Other"

# Title keyword rules, checked in this order; the first match wins.
# Patterns run on job_title_clean (uppercase, punctuation removed).
TITLE_RULES: list[tuple[str, str]] = [
    ("Data Scientist", r"\bDATA SCIEN|\bDECISION SCIEN"),
    ("ML/AI Engineer",
     r"\bMACHINE LEARNING\b|\bML\b|\bMLOPS\b|\bAI\b|\bGENAI\b|\bGEN AI\b|"
     r"ARTIFICIAL INTELLIGENCE|\bDEEP LEARNING\b|\bNLP\b|NATURAL LANGUAGE PROCESSING|"
     r"\bCOMPUTER VISION\b|\bLLMS?\b"),
    ("Data Engineer",
     r"\bDATA ENGINEER|\bBIG DATA\b|\bDATA ARCHITECT|\bDATA WAREHOUS|\bETL\b|"
     r"\bDATA PLATFORM|\bDATA PIPELINE|\bANALYTICS ENGINEER|\bDATA INTEGRATION|"
     r"\bDATA DEVELOPER|\bDATA MODELER|\bDATA MODELLER"),
    ("Statistician/Quant",
     r"\bSTATISTIC|\bBIOSTATISTIC|\bQUANT\b|\bQUANTITATIVE|\bECONOMETRIC|"
     r"\bOPERATIONS RESEARCH"),
    ("Data Analyst/BI",
     r"\bDATA ANALY|\bANALYTICS\b|\bANALYTIC\b|\bBUSINESS INTELLIGENCE\b|\bBUSINESS INTEL\b|\bBI\b|"
     r"\bPOWER BI\b|\bTABLEAU\b|\bREPORTING ANALYST|\bINSIGHTS ANALYST|"
     r"\bDATA VISUALI|\bDATA INSIGHT"),
]

# Extra rules used ONLY for rows whose SOC code is already a core data code.
# 'Business Analyst' is too broad to pull rows in from other SOC codes, but
# when the employer filed it as 15-2051 (Data Scientists / BI Analysts) it is
# closer to an analyst role than a data scientist one.
CORE_ONLY_TITLE_RULES: list[tuple[str, str]] = [
    ("Data Analyst/BI", r"\bBUSINESS ANALYST|\bBUSINESS SYSTEMS ANALYST|\bREPORTING\b"),
]

# Titles matching any of these never count as a data role from keywords alone.
TITLE_EXCLUSIONS = (
    r"\bDATA ENTRY\b|\bDATABASE ADMIN|\bDBA\b|\bDATA CENT(?:ER|RE)\b|\bDATACENTER\b|"
    r"\bANALYTICAL (?:CHEMIST|CHEMISTRY|SCIENTIST|SCIENCES?|DEVELOPMENT|LAB|METHOD)|"
    r"\bCLINICAL DATA (?:MANAGER|COORDINATOR|ASSOCIATE)"
)

# Titles that carry no data meaning on their own. A row with a core data SOC
# code is still kept as a data role (the employer told DOL it is one), but if
# its title has no data keyword AND matches this list it gets
# title_is_generic = TRUE so dashboards can filter it out (e.g. on the
# "Top sponsors for your title" page). Rows are flagged, never dropped.
GENERIC_TITLE_PATTERNS = (
    r"^(?:(?:SENIOR|JUNIOR|LEAD|PRINCIPAL|STAFF|ASSOCIATE) )*(?:ASSOCIATE|ANALYST|CONSULTANT|MANAGER|DIRECTOR|ENGINEER|SCIENTIST|"
    r"RESEARCH|SPECIALIST|ADVISOR|PARTNER|PRINCIPAL|MEMBER OF TECHNICAL(?: STAFF)?|"
    r"(?:SENIOR |ASSISTANT |EXECUTIVE )?VICE PRESIDENT|OFFICER)$|"
    r"\bPRODUCT MANAGE|\bBUSINESS MANAGER\b|\bPROGRAM MANAGE|\bPROJECT MANAGE|"
    r"\bSOFTWARE (?:ENGINEER|DEVELOPER)\b|\bTRADER\b|\bFINANCIAL ANALYST\b|"
    r"\bSTRATEGY AND OPERATIONS\b|\bBUSINESS DEVELOPER\b|\bDEPLOYMENT STRATEGIST\b"
)

# SOC codes that ARE data roles. The family is taken from the title when a
# title rule matches, otherwise from this default.
CORE_SOC_DEFAULT = {
    "15-2051.00": "Data Scientist",          # Data Scientists
    "15-2051.01": "Data Analyst/BI",         # Business Intelligence Analysts
    "15-2041.00": "Statistician/Quant",      # Statisticians
    "15-2041.01": "Statistician/Quant",      # Biostatisticians
    "15-2031.00": "Statistician/Quant",      # Operations Research Analysts
    "13-2099.01": "Statistician/Quant",      # Financial Quantitative Analysts
    "15-1243.01": "Data Engineer",           # Data Warehousing Specialists
}

# SOC groups where a data role is plausible but the code alone is too broad.
# Rows here count only when the TITLE matches a rule (and no exclusion).
# 15-1252 Software Developers is the big one (many Data/ML Engineers).
GATED_SOC_PREFIXES = (
    "15-1",       # all computer occupations: 15-1252, 15-1221, 15-1243, 15-1211, 15-1299 ...
    "15-2",       # other math occupations not in CORE (e.g. 15-2051.02, 15-2011)
    "11-3021",    # Computer and Information Systems Managers
    "11-2021",    # Marketing Managers
    "13-1111",    # Management Analysts
    "13-1161",    # Market Research Analysts
    "13-2051",    # Financial and Investment Analysts
    "13-2099",    # Financial Specialists, All Other
    "13-1199",    # Business Operations Specialists, All Other
    "19-1029",    # Biological Scientists, All Other (bioinformatics)
    "19-3011",    # Economists
)


def title_family(title_clean: pd.Series, rules=None) -> pd.Series:
    """Family from title keywords alone (NA when no rule matches)."""
    rules = TITLE_RULES if rules is None else rules
    fam = pd.Series(pd.NA, index=title_clean.index, dtype="string")
    for name, pat in reversed(rules):  # reversed so earlier rules overwrite
        hit = title_clean.str.contains(pat, regex=True).fillna(False)
        fam[hit] = name
    return fam


def classify_roles(df: pd.DataFrame) -> pd.DataFrame:
    """Add role_family, role_match_reason and is_data_role.

    Logic, in plain words:
      1. Core data SOC code  -> always a data role; family from the title if a
         title rule matches, else the SOC default. (reason 'soc' / 'soc+title')
      2. Gated SOC code (e.g. 15-1252 Software Developers) -> a data role only
         if the title matches a rule and no exclusion. (reason 'title')
      3. Everything else -> 'Other'. Titles are not used outside the gated
         list, to avoid e.g. lab 'analytics' or 'AI' in unrelated fields.
    """
    out = df.copy()
    t = out["job_title_clean"].fillna("")
    fam_t = title_family(t)
    excluded = t.str.contains(TITLE_EXCLUSIONS, regex=True).fillna(False)
    out["title_family"] = fam_t
    out["title_excluded"] = excluded

    soc8 = out["soc_8"].astype("string")
    soc_default = soc8.map(CORE_SOC_DEFAULT).astype("string")
    is_core = soc_default.notna()
    is_gated = (~is_core) & soc8.str.startswith(GATED_SOC_PREFIXES).fillna(False)

    title_ok = fam_t.notna() & ~excluded

    family = pd.Series(OTHER, index=out.index, dtype="string")
    reason = pd.Series("none", index=out.index, dtype="string")

    # Inside core SOC codes only, also try the core-only rules.
    fam_core = fam_t.fillna(title_family(t, CORE_ONLY_TITLE_RULES))
    title_ok_core = fam_core.notna() & ~excluded

    core_title = is_core & title_ok_core
    core_only = is_core & ~title_ok_core
    gated_hit = is_gated & title_ok

    family[core_only] = soc_default[core_only]
    reason[core_only] = "soc"
    family[core_title] = fam_core[core_title]
    reason[core_title] = "soc+title"
    family[gated_hit] = fam_t[gated_hit]
    reason[gated_hit] = "title"

    out["role_family"] = family
    out["role_match_reason"] = reason
    base = out["job_title_base"].fillna("") if "job_title_base" in out else t
    generic = base.str.contains(GENERIC_TITLE_PATTERNS, regex=True).fillna(False)
    out["title_is_generic"] = core_only & generic
    out["is_data_role"] = family.ne(OTHER)
    out.attrs = dict(df.attrs)
    return out


# ---------------------------------------------------------------------------
# 8. Output
# ---------------------------------------------------------------------------

OUTPUT_COLUMNS = [
    "CASE_NUMBER", "CASE_STATUS", "VISA_CLASS", "is_h1b", "is_certified", "is_certified_h1b",
    "RECEIVED_DATE", "DECISION_DATE", "decision_fy", "decision_fq",
    "source_file", "source_fy", "source_quarter",
    "EMPLOYER_NAME", "employer_name_clean", "employer_name_std", "EMPLOYER_FEIN", "fein_valid",
    "TRADE_NAME_DBA", "EMPLOYER_CITY", "EMPLOYER_STATE", "NAICS_CODE",
    "JOB_TITLE", "job_title_clean", "job_title_base",
    "SOC_CODE", "SOC_TITLE", "soc_6", "soc_8", "soc_valid",
    "role_family", "role_match_reason", "title_is_generic",
    "FULL_TIME_POSITION", "BEGIN_DATE", "END_DATE", "TOTAL_WORKER_POSITIONS",
    "NEW_EMPLOYMENT", "CONTINUED_EMPLOYMENT", "CHANGE_EMPLOYER",
    "WORKSITE_CITY", "WORKSITE_COUNTY", "WORKSITE_STATE", "WORKSITE_POSTAL_CODE",
    "WAGE_RATE_OF_PAY_FROM", "WAGE_RATE_OF_PAY_TO", "WAGE_UNIT_OF_PAY",
    "wage_annual_from", "wage_annual_to", "PREVAILING_WAGE", "PW_UNIT_OF_PAY", "pw_annual",
    "wage_vs_pw_pct", "wage_flag", "PW_WAGE_LEVEL",
    "H_1B_DEPENDENT", "WILLFUL_VIOLATOR",
]


def to_output(df: pd.DataFrame) -> pd.DataFrame:
    """Keep data roles only, in a fixed column order, lower-case names."""
    out = df.loc[df["is_data_role"], OUTPUT_COLUMNS].copy()
    out.columns = [c.lower() for c in out.columns]
    return out.reset_index(drop=True)


def save_outputs(df: pd.DataFrame, out_dir: str | Path, stem: str) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"parquet": out_dir / f"{stem}.parquet", "csv": out_dir / f"{stem}.csv"}
    df.to_parquet(paths["parquet"], index=False)
    df.to_csv(paths["csv"], index=False, date_format="%Y-%m-%d")
    return paths


def clean_quarter(raw: pd.DataFrame) -> pd.DataFrame:
    """All cleaning steps on one raw quarter; returns every row (not just
    data roles) so checks can compare matched vs. unmatched rows."""
    df = select_columns(raw)
    df = add_status_and_dates(df)
    df = normalize_soc(df)
    df = annualize_wages(df)
    df = standardize_employers(df)
    df = normalize_titles(df)
    df = classify_roles(df)
    return df


def run_pipeline(xlsx_path: str | Path, out_dir: str | Path, cache_dir: str | Path | None = None) -> pd.DataFrame:
    """Load, clean, filter to data roles and save .parquet + .csv."""
    raw = load_quarter(xlsx_path, cache_dir=cache_dir)
    full = clean_quarter(raw)
    out = to_output(full)
    fy, q = parse_file_period(xlsx_path)
    stem = f"lca_roles_fy{fy}q{q}" if fy else "lca_roles"
    save_outputs(out, out_dir, stem)
    return out


# Note on combining quarters: DOL files are NOT consistently cumulative. Some
# cover the fiscal year to date (FY2026_Q3 = Oct 1 - Jun 30), others only their
# own quarter (FY2024_Q4 and FY2025_Q4 = Jul 1 - Sep 30). So we union every file
# and, where a case_number appears more than once, keep the row from the most
# recent source file (highest fiscal year, then quarter). This is correct either way.
def combine_quarters(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Union cleaned quarter frames; dedupe case_number keeping the newest source file's row."""
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return pd.DataFrame()
    allq = pd.concat(frames, ignore_index=True)
    if "source_file" not in allq.columns:
        allq["source_file"] = None
    for c in ("source_fy", "source_quarter"):
        if c not in allq.columns:
            allq[c] = None
    # Fill missing period columns from the file name where possible.
    parsed = allq["source_file"].map(lambda f: parse_file_period(f) if isinstance(f, str) else (None, None))
    allq["source_fy"] = pd.to_numeric(allq["source_fy"], errors="coerce").fillna(parsed.str[0])
    allq["source_quarter"] = pd.to_numeric(allq["source_quarter"], errors="coerce").fillna(parsed.str[1])
    allq["source_fy"] = pd.to_numeric(allq["source_fy"], errors="coerce").astype("Int64")
    allq["source_quarter"] = pd.to_numeric(allq["source_quarter"], errors="coerce").astype("Int64")
    # Stable sort, unknown periods first, so the newest file's row is last for each case.
    allq = allq.sort_values(["source_fy", "source_quarter"], na_position="first", kind="mergesort")
    return allq.drop_duplicates("case_number", keep="last").reset_index(drop=True)
