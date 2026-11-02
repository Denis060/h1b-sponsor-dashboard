# Data Dictionary

Output of `notebooks/01_clean_lca.ipynb` / `src/clean_lca.py`:
`data/processed/lca_roles_fy2026q3.parquet` and `.csv` (one row per LCA case, data / ML / analytics roles only).

Source: U.S. Department of Labor, OFLC, LCA Programs (H-1B, H-1B1, E-3) disclosure data. Raw columns are
confirmed against the DOL OFLC record layout for each fiscal year (FY2026 Q3 layout used here).
An LCA is an employer filing, not an approved H-1B petition. Informational only, not legal advice.

**Source** column: `DOL` = copied from the DOL file (text, trimmed, column name lowercased); `derived` = created by the pipeline.

| Column | Source | Type | Description |
|---|---|---|---|
| case_number | DOL | text | Unique LCA case ID. Primary key. |
| case_status | DOL | text | Certified, Certified - Withdrawn, Withdrawn, Denied. |
| visa_class | DOL | text | H-1B, E-3 Australian, H-1B1 Chile, H-1B1 Singapore. |
| is_h1b | derived | bool | visa_class = 'H-1B'. |
| is_certified | derived | bool | case_status = 'Certified' (excludes Certified - Withdrawn). |
| is_certified_h1b | derived | bool | is_h1b AND is_certified. Main filter for sponsor counts. |
| received_date | DOL | date | Date DOL received the LCA. |
| decision_date | DOL | date | Date of DOL's decision. |
| decision_fy | derived | int | Federal fiscal year of decision_date (Oct 1 – Sep 30; Oct 2025 = FY2026). |
| decision_fq | derived | int | Fiscal quarter of decision_date (Q1 = Oct–Dec … Q4 = Jul–Sep). |
| source_file | derived | text | DOL file the row came from. |
| source_fy | derived | int | Fiscal year in the file name. |
| source_quarter | derived | int | Quarter in the file name. DOL files are cumulative within a fiscal year. |
| employer_name | DOL | text | Employer legal name as filed. |
| employer_name_clean | derived | text | Uppercase, '&' to AND, punctuation removed, leading THE and trailing legal forms (INC, LLC, CORP, CO, LTD, LP, LLP, NA …) removed. |
| employer_name_std | derived | text | One name per FEIN: the most common employer_name_clean filed under that FEIN. Use this for employer rankings. |
| employer_fein | DOL | text | Federal Employer Identification Number (NN-NNNNNNN). Identifies a legal entity, not a brand. |
| fein_valid | derived | bool | FEIN matches NN-NNNNNNN and is not all zeros. |
| trade_name_dba | DOL | text | "Doing business as" name, if any. |
| employer_city | DOL | text | Employer HQ city. |
| employer_state | DOL | text | Employer HQ state. |
| naics_code | DOL | text | Employer industry code (NAICS). |
| job_title | DOL | text | Job title as filed. |
| job_title_clean | derived | text | Uppercase, punctuation to spaces, abbreviations expanded (SR→SENIOR, ENGR→ENGINEER, VP→VICE PRESIDENT …). |
| job_title_base | derived | text | job_title_clean without seniority/level words (SENIOR, LEAD, PRINCIPAL, STAFF, II, 3, L5 …) or text in brackets. For "top sponsors for your title". |
| soc_code | DOL | text | SOC occupation code as filed (sometimes malformed). |
| soc_title | DOL | text | SOC occupation title as filed. |
| soc_6 | derived | text | 6-digit SOC code, e.g. 15-2051. |
| soc_8 | derived | text | Detailed SOC code, e.g. 15-2051.01 (missing suffix becomes .00). |
| soc_valid | derived | bool | soc_code could be parsed. Always true in the output. |
| role_family | derived | text | Data Scientist, ML/AI Engineer, Data Engineer, Statistician/Quant, Data Analyst/BI. Rules in src/clean_lca.py (CORE_SOC_DEFAULT, GATED_SOC_PREFIXES, TITLE_RULES, TITLE_EXCLUSIONS). |
| role_match_reason | derived | text | Why the row is a data role: `soc` (core SOC code, title gave no family), `soc+title` (core SOC and title rule), `title` (broad SOC code such as 15-1252, title rule matched). |
| full_time_position | DOL | text | Y/N. |
| begin_date | DOL | date | Employment start date on the LCA. |
| end_date | DOL | date | Employment end date on the LCA. |
| total_worker_positions | DOL | int | Number of workers requested on the LCA. |
| new_employment | DOL | text | Workers requested for new employment. |
| continued_employment | DOL | text | Workers requested for continuation. |
| change_employer | DOL | text | Workers requested for change of employer. |
| worksite_city | DOL | text | Primary worksite city. |
| worksite_county | DOL | text | Primary worksite county. |
| worksite_state | DOL | text | Primary worksite state (2-letter). Use for the state slicer. |
| worksite_postal_code | DOL | text | Primary worksite ZIP (kept as text to keep leading zeros). |
| wage_rate_of_pay_from | DOL | text | Offered wage, lower end, in wage_unit_of_pay (raw). |
| wage_rate_of_pay_to | DOL | text | Offered wage, upper end (raw, often blank). |
| wage_unit_of_pay | DOL | text | Year, Hour, Week, Bi-Weekly, Month. |
| wage_annual_from | derived | number | Lower offered wage in annual USD. Hour×2080, Week×52, Bi-Weekly×26, Month×12. Main wage measure. |
| wage_annual_to | derived | number | Upper offered wage in annual USD; blank when no range, or when 0 or below the lower end. |
| prevailing_wage | DOL | text | Prevailing wage (raw). |
| pw_unit_of_pay | DOL | text | Unit of the prevailing wage. |
| pw_annual | derived | number | Prevailing wage in annual USD (same factors). |
| wage_vs_pw_pct | derived | number | (wage_annual_from / pw_annual − 1) × 100. |
| wage_flag | derived | text | `ok`; `unit_assumed_year` (non-yearly unit but rate ≥ 15,000, treated as yearly); `below_20k`; `above_1m`; `missing`; `unknown_unit`. Exclude below_20k / above_1m from wage visuals. |
| pw_wage_level | DOL | text | I–IV, or `Not reported` when blank. |
| h_1b_dependent | DOL | text | Y/N: employer is H-1B dependent. Raw column is H_1B_DEPENDENT (H-1B_DEPENDENT in the PDF layout). |
| willful_violator | DOL | text | Y/N: employer was found a willful violator. |

Dropped on purpose: point-of-contact, attorney, law firm and preparer names, emails and phone numbers (not needed; repo is public).
