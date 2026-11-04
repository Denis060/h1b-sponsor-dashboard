-- 02_wages_by_role_level.sql
-- Question: For each role family, what is the typical offered salary (25th / median / 75th percentile)
-- at each DOL prevailing-wage level (I = entry ... IV = fully competent)?
-- Also shows how far offers sit above the prevailing wage (median wage_vs_pw_pct).
-- Certified H-1B only; rows flagged above_1m excluded. Informational only.

SELECT role_family,
       pw_wage_level,
       count(*) AS filings,
       round(percentile_cont(0.25) WITHIN GROUP (ORDER BY wage_annual_from)::numeric, 0) AS p25_wage,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY wage_annual_from)::numeric, 0) AS median_wage,
       round(percentile_cont(0.75) WITHIN GROUP (ORDER BY wage_annual_from)::numeric, 0) AS p75_wage,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY wage_vs_pw_pct)::numeric, 1)   AS median_pct_above_pw
FROM public.lca_roles
WHERE is_certified_h1b
  AND wage_flag <> 'above_1m'
GROUP BY role_family, pw_wage_level
ORDER BY role_family,
         CASE pw_wage_level WHEN 'I' THEN 1 WHEN 'II' THEN 2 WHEN 'III' THEN 3 WHEN 'IV' THEN 4 ELSE 5 END;
