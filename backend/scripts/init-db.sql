-- =============================================================================
-- EduVision AI — Database Initialization Script
-- =============================================================================
-- This script runs on first PostgreSQL container startup via init-db mechanism.
-- =============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS eduvision;

-- Set search path
SET search_path TO eduvision, public;

-- Create auditor role (reserved for future use)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'auditor') THEN
        CREATE ROLE auditor WITH LOGIN PASSWORD 'auditor' INHERIT;
    END IF;
END
$$;
