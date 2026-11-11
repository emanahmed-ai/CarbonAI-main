# Database schema (SQLite, `db/schema.py`)

    countries(country_id PK, iso2_code UNIQUE, iso3_code UNIQUE, name_ar, name_en, region, is_active)
    sources(reference_id PK, organization_name, document_title, source_url, document_url, publication_year,
            license_or_usage_notes, last_checked_at, verification_status, country_id -> countries)
    emission_factors(PK factor_id+version, country_code [ISO2|GLOBAL|REGION:xx], factor_class, activity_category,
            activity, activity_unit, co2e_factor_value (text Decimal), components_json, gwp_set_id,
            reference_id -> sources, source_*, year_from, year_to, verification_status, verified_by, last_verified_at, ...)
    factor_audit_log(log_id PK, factor_id, version, action, field_name, old_value, new_value, changed_at,
            changed_by, reason, reference_id)
    activity_categories(category_key PK, name_ar, name_en, expected_scope(hint only), compatible_units, ...)
    companies(company_id PK, name+country UNIQUE, boundary_approach, boundary_notes)
    facilities(facility_id PK, company_id -> companies, name, control_status)
    activity_records(record_id PK, fingerprint UNIQUE, company_id, facility_id, activity_date (nullable), year, month,
            quantity, unit, category_key, scope, scope_status, scope_confidence, scope_reason, scope_missing_info,
            scope3_category, scope2_method, factor snapshot columns (id, version, value, unit, source, url, class,
            verification, snapshot_json), kg_co2e, t_co2e, calc_status, calc_notes, engine_version, origin)
    scope_audit_log(record_id -> activity_records, old/new scope, reason, changed_at, changed_by)
    import_batches / import_rejections, reduction_plans, settings, update_log, schema_meta

Relationships: factors -> sources; records -> companies/facilities; records keep a *copy* (snapshot) of the factor
so editing or superseding a factor never changes a stored result. Old factor versions are never deleted.

Why SQLite and not PostgreSQL: the supplied project listed PostgreSQL/SQLAlchemy/Alembic as a target stack but none of
it was implemented, and no DB existed, so SQLite (stdlib) was used as the brief allows. To move to PostgreSQL later,
port `db/schema.py` DDL (types are plain TEXT/INTEGER) and the `?` placeholders; the service layer is the only SQL user.
Decimals are stored as text to avoid binary-float error.
