-- 03_geography.sql
-- Question: Where are certified H-1B data / ML / analytics jobs located, and what do they pay there?
-- A: by worksite state; B: top 25 worksite cities overall; C: top 5 cities per role family.
-- Certified H-1B only; median excludes rows flagged above_1m. Informational only.

-- A. By worksite state
SELECT worksite_state,
       count(*) AS filings,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
             FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0) AS median_wage
FROM public.lca_roles
WHERE is_certified_h1b
GROUP BY worksite_state
ORDER BY filings DESC;

-- B. Top 25 worksite cities
SELECT initcap(worksite_city) AS worksite_city, worksite_state,
       count(*) AS filings,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
             FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0) AS median_wage
FROM public.lca_roles
WHERE is_certified_h1b
GROUP BY initcap(worksite_city), worksite_state
ORDER BY filings DESC
LIMIT 25;

-- C. Top 5 cities per role family
WITH c AS (
    SELECT role_family, initcap(worksite_city) AS worksite_city, worksite_state,
           count(*) AS filings,
           round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
                 FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0) AS median_wage
    FROM public.lca_roles
    WHERE is_certified_h1b
    GROUP BY role_family, initcap(worksite_city), worksite_state
)
SELECT role_family, rnk, worksite_city, worksite_state, filings, median_wage
FROM (SELECT c.*, row_number() OVER (PARTITION BY role_family ORDER BY filings DESC) AS rnk FROM c) r
WHERE rnk <= 5
ORDER BY role_family, rnk;
