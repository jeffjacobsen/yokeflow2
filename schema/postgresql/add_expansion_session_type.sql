-- Migration: Add 'expansion' to session_type enum
-- Required for parallel initialization (expansion workers)
-- Run this on existing databases. Safe to run multiple times.

ALTER TYPE session_type ADD VALUE IF NOT EXISTS 'expansion' AFTER 'initializer';
