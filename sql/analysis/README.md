# Analysis queries

Run in the Supabase SQL Editor (or `psql`) against `public.lca_roles`. Certified H-1B rows only
(`is_certified_h1b`) unless noted. Wages are `wage_annual_from`; medians use `percentile_cont` and exclude
the 2 rows flagged `above_1m`. Snippets below are from a test run on FY2026 Q3 data only
(55,204 rows, 50,380 certified H-1B). An LCA is an employer filing, not an approved petition.
Informational only, not legal advice.

| File | Question |
|---|---|
| `01_top_sponsors.sql` | Top employers overall and top 10 per role family (filings, positions, median wage) |
| `02_wages_by_role_level.sql` | p25 / median / p75 wage by role family and prevailing-wage level |
| `03_geography.sql` | Filings and median wage by worksite state, top cities, top cities per role family |
| `04_titles.sql` | Top 10 base job titles per role family, with employer count and median wage |
| `05_trends.sql` | Filings, median wage and share per role family by decision fiscal year / quarter |
| `06_status_mix.sql` | Certified / certified-withdrawn / withdrawn / denied share per employer (all rows, 50+ filings) |
| `07_views.sql` | Power BI views: `v_sponsor_role_summary`, `v_geo_summary`, `v_title_summary`, `v_wage_level_summary`, `v_employer_status_mix` |

## Test snippets (FY2026 Q3 file)

**01 top sponsors**
| employer | filings | median wage |
|---|---|---|
| AMAZON COM SERVICES | 1,733 | $142,000 |
| META PLATFORMS | 827 | $207,325 |
| JPMORGAN CHASE | 671 | $150,000 |
| WAL MART ASSOCIATES | 664 | $145,553 |
| APPLE | 560 | $181,100 |

**02 wages by level (median)**
| role family | I | II | III | IV |
|---|---|---|---|---|
| Data Analyst/BI | $81,598 | $104,925 | $130,400 | $159,099 |
| Data Scientist | $94,764 | $115,939 | $145,308 | $174,564 |
| ML/AI Engineer | $127,712 | $144,375 | $173,621 | $212,202 |

**03 geography (states)**: CA 9,669 filings ($172,437), TX 7,382 ($113,919), NY 6,096 ($152,339), WA 3,447 ($159,002).
Top city: New York, NY 5,162 filings ($160,000).

**04 titles**: DATA ANALYST 2,561 filings across 1,379 employers ($96,034); DATA ENGINEER 6,174 across 2,232 ($124,488);
DATA SCIENTIST 5,126 across 1,904 ($134,612).

**05 trends** (FY2026, certified H-1B filings): Q1 7,957, Q2 12,424, Q3 29,999.

**06 status mix**: Amazon 1,748 filings, 100% certified; Apple 678, 16.5% certified-then-withdrawn; PayPal 250, 36.0% certified-then-withdrawn.

**07 views**: `v_sponsor_role_summary` 16,886 rows and `v_geo_summary` 5,874 rows; both sum to 50,380 filings.
In Power BI, sum `filings` across rows but never average `median_wage`.
