# H-1B Sponsor Intelligence Dashboard

Which employers sponsor H-1B visas for data, ML and analytics roles, what they pay, where, and how that changes over time. Built from public U.S. Department of Labor LCA disclosure data and the USCIS H-1B Employer Data Hub.

**Live dashboard:** _coming soon_

## Questions this answers
- Who are the top sponsors for a given data job title?
- What do they pay, by title, city, and state?
- How is sponsorship changing year over year?

## Stack
Python (pandas) for ingestion and cleaning · PostgreSQL (Supabase) for analysis · Excel for sanity checks · Power BI for the dashboard

## Data sources
- [DOL OFLC Performance Data](https://www.dol.gov/agencies/eta/foreign-labor/performance) (LCA disclosure files)
- [USCIS H-1B Employer Data Hub](https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub)

## Repo layout
```
data/        raw and processed files (not committed)
notebooks/   pandas ingestion and cleaning
sql/schema/  table definitions
sql/analysis/ analysis queries
excel/       sanity-check workbooks
powerbi/     .pbix report
docs/        data dictionary and methodology
screenshots/ dashboard images
app/         optional Streamlit search app
```

## Methodology
_To be written: cleaning rules, role filter, wage annualization._

## Key findings
_To be added after analysis._

## Disclaimer
This is an informational project using public data. It is not legal or immigration advice. An LCA filing does not mean an H-1B petition was approved.
