-- 05_trends.sql
-- Question: How do certified H-1B data-role filings and median wages change over time?
-- Grouped by federal fiscal year / quarter of the decision date, per role family.
-- With only FY2026 Q1-Q3 loaded this shows quarters; it becomes a multi-year trend once FY2024-25 load.
-- Note: filings in a quarter depend on DOL processing timing, not only on hiring demand. Informational only.

SELECT decision_fy, decision_fq, role_family,
       count(*) AS filings,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
             FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0) AS median_wage,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY decision_fy, decision_fq), 1) AS pct_of_quarter
FROM public.lca_roles
WHERE is_certified_h1b
GROUP BY decision_fy, decision_fq, role_family
ORDER BY decision_fy, decision_fq, role_family;
