-- 01_top_sponsors.sql
-- Question: Which employers file the most certified H-1B LCAs for data / ML / analytics roles,
-- overall and within each role family, and what do they offer (median annual wage)?
-- Filings = LCA cases (one case can cover several positions). An LCA is not an approved petition.
-- Wages: wage_annual_from, excluding rows flagged above_1m. Informational only, not legal advice.

-- A. Top 25 sponsors overall
SELECT employer_name_std,
       count(*)                                                        AS filings,
       sum(total_worker_positions)                                     AS positions,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
             FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0)       AS median_wage
FROM public.lca_roles
WHERE is_certified_h1b
GROUP BY employer_name_std
ORDER BY filings DESC
LIMIT 25;

-- B. Top 10 sponsors per role family
WITH s AS (
    SELECT role_family, employer_name_std,
           count(*) AS filings,
           round(percentile_cont(0.5) WITHIN GROUP (ORDER BY wage_annual_from)
                 FILTER (WHERE wage_flag <> 'above_1m')::numeric, 0) AS median_wage
    FROM public.lca_roles
    WHERE is_certified_h1b
    GROUP BY role_family, employer_name_std
)
SELECT role_family, rnk, employer_name_std, filings, median_wage
FROM (SELECT s.*, row_number() OVER (PARTITION BY role_family ORDER BY filings DESC, employer_name_std) AS rnk FROM s) r
WHERE rnk <= 10
ORDER BY role_family, rnk;
