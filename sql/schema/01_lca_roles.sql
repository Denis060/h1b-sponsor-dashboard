-- lca_roles: one row per DOL LCA case, data / ML / analytics roles only.
-- Built from data/processed/lca_roles_fy*.parquet (see docs/data_dictionary.md).
-- An LCA is an employer filing, not an approved H-1B petition. Informational only, not legal advice.
-- Safe to re-run: every statement is IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS public.lca_roles (
    case_number             text PRIMARY KEY,
    case_status             text,
    visa_class              text,
    is_h1b                  boolean NOT NULL,
    is_certified            boolean NOT NULL,
    is_certified_h1b        boolean NOT NULL,
    received_date           date,
    decision_date           date,
    decision_fy             smallint,   -- federal fiscal year of decision_date (the "year" slicer)
    decision_fq             smallint,
    source_file             text,
    source_fy               smallint,
    source_quarter          smallint,
    employer_name           text,
    employer_name_clean     text,
    employer_name_std       text,       -- use for employer rankings
    employer_fein           text,
    fein_valid              boolean,
    trade_name_dba          text,
    employer_city           text,
    employer_state          text,
    naics_code              text,
    job_title               text,
    job_title_clean         text,
    job_title_base          text,
    soc_code                text,
    soc_title               text,
    soc_6                   text,
    soc_8                   text,
    soc_valid               boolean,
    role_family             text,
    role_match_reason       text,
    full_time_position      text,
    begin_date              date,
    end_date                date,
    total_worker_positions  integer,
    new_employment          integer,
    continued_employment    integer,
    change_employer         integer,
    worksite_city           text,
    worksite_county         text,
    worksite_state          text,
    worksite_postal_code    text,       -- text keeps leading zeros
    wage_rate_of_pay_from   text,       -- raw, as filed
    wage_rate_of_pay_to     text,
    wage_unit_of_pay        text,
    wage_annual_from        numeric(12,2),
    wage_annual_to          numeric(12,2),
    prevailing_wage         text,
    pw_unit_of_pay          text,
    pw_annual               numeric(12,2),
    wage_vs_pw_pct          numeric(9,2),
    wage_flag               text,
    pw_wage_level           text,
    h_1b_dependent          text,
    willful_violator        text,
    loaded_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_lca_roles_employer_std     ON public.lca_roles (employer_name_std);
CREATE INDEX IF NOT EXISTS ix_lca_roles_role_family      ON public.lca_roles (role_family);
CREATE INDEX IF NOT EXISTS ix_lca_roles_worksite_state   ON public.lca_roles (worksite_state);
CREATE INDEX IF NOT EXISTS ix_lca_roles_decision_fy      ON public.lca_roles (decision_fy);
CREATE INDEX IF NOT EXISTS ix_lca_roles_is_certified_h1b ON public.lca_roles (is_certified_h1b);
