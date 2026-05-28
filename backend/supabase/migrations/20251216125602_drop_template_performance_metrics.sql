-- Migration: Drop unused template_performance_metrics table
-- Date: 2025-12-16
-- Description: Remove table that is not used anywhere in the application code.

DROP TABLE IF EXISTS template_performance_metrics;
