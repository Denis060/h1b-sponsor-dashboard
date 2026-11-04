-- 04_titles.sql
-- Question: Which job titles appear most often in each role family, and what do they pay?
-- Uses job_title_base (normalized title with seniority words stripped, see data dictionary).
-- Top 10 titles per role family. Certified H-1B only; median excludes above_1m. Informational only.

WITH t AS (
    SELECT role_family, job_title_base,
           count(*) AS filings,
           count(DISTINCT employer_name_std) AS employers,
           round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
                 FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0) AS median_wage
    FROM public.lca_roles
    WHERE is_certified_h1b
    GROUP BY role_family, job_title_base
)
SELECT role_family, rnk, job_title_base, filings, employers, median_wage
FROM (SELECT t.*, row_number() OVER (PARTITION BY role_family ORDER BY filings DESC, job_title_base) AS rnk FROM t) r
WHERE rnk <= 10
ORDER BY role_family, rnk;
