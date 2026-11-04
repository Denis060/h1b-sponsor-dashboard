-- 06_status_mix.sql
-- Question: For each employer (all visa classes and statuses), what share of its data-role LCAs were
-- certified, certified-then-withdrawn, withdrawn, or denied? Limited to employers with 50+ filings.
-- A high withdrawn share is not a red flag by itself (plans change); denials are rare. Informational only.

SELECT employer_name_std,
       count(*) AS filings,
       round(100.0 * count(*) FILTER (WHERE case_status = 'Certified') / count(*), 1)             AS pct_certified,
       round(100.0 * count(*) FILTER (WHERE case_status = 'Certified - Withdrawn') / count(*), 1) AS pct_cert_withdrawn,
       round(100.0 * count(*) FILTER (WHERE case_status = 'Withdrawn') / count(*), 1)             AS pct_withdrawn,
       round(100.0 * count(*) FILTER (WHERE case_status = 'Denied') / count(*), 1)                AS pct_denied
FROM public.lca_roles
GROUP BY employer_name_std
HAVING count(*) >= 50
ORDER BY filings DESC;
