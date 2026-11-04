-- 07_views.sql
-- Views for Power BI (Import mode). Each is pre-aggregated at a grain that keeps role / state / year
-- slicers working. Certified H-1B only unless noted. Medians exclude rows flagged above_1m.
-- Medians cannot be re-aggregated in Power BI: when a slicer combines rows, sum filings but do NOT
-- average medians (compute medians from the row-level table or show them at the view's grain).

-- Employer x role family x fiscal year: feeds the "Top sponsors for your title" page.
CREATE OR REPLACE VIEW public.v_sponsor_role_summary AS
SELECT decision_fy, role_family, employer_name_std,
       count(*) AS filings,
       sum(total_worker_positions) AS positions,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
             FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0) AS median_wage
FROM public.lca_roles
WHERE is_certified_h1b
GROUP BY decision_fy, role_family, employer_name_std;

-- State x city x role family x fiscal year.
CREATE OR REPLACE VIEW public.v_geo_summary AS
SELECT decision_fy, role_family, worksite_state, initcap(worksite_city) AS worksite_city,
       count(*) AS filings,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
             FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0) AS median_wage
FROM public.lca_roles
WHERE is_certified_h1b
GROUP BY decision_fy, role_family, worksite_state, initcap(worksite_city);

-- Base title x role family x fiscal year.
CREATE OR REPLACE VIEW public.v_title_summary AS
SELECT decision_fy, role_family, job_title_base,
       count(*) AS filings,
       count(DISTINCT employer_name_std) AS employers,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
             FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0) AS median_wage
FROM public.lca_roles
WHERE is_certified_h1b
GROUP BY decision_fy, role_family, job_title_base;

-- Role family x wage level x fiscal year with p25 / median / p75.
CREATE OR REPLACE VIEW public.v_wage_level_summary AS
SELECT decision_fy, role_family, pw_wage_level,
       count(*) AS filings,
       round(percentile_cont(0.25) WITHIN GROUP (ORDER BY wage_annual_from)::numeric, 0) AS p25_wage,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY wage_annual_from)::numeric, 0) AS median_wage,
       round(percentile_cont(0.75) WITHIN GROUP (ORDER BY wage_annual_from)::numeric, 0) AS p75_wage
FROM public.lca_roles
WHERE is_certified_h1b AND wage_flag <> 'above_1m'
GROUP BY decision_fy, role_family, pw_wage_level;

-- Employer status mix (ALL rows, all statuses), employers with 20+ filings.
CREATE OR REPLACE VIEW public.v_employer_status_mix AS
SELECT employer_name_std,
       count(*) AS filings,
       count(*) FILTER (WHERE case_status = 'Certified')             AS certified,
       count(*) FILTER (WHERE case_status = 'Certified - Withdrawn') AS certified_withdrawn,
       count(*) FILTER (WHERE case_status = 'Withdrawn')             AS withdrawn,
       count(*) FILTER (WHERE case_status = 'Denied')                AS denied
FROM public.lca_roles
GROUP BY employer_name_std
HAVING count(*) >= 20;
