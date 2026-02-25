# 🚨 BREAKING CHANGE - Fresh Installation Required

## YokeFlow v2.1.0 - Database Schema Update

**Effective Date**: February 2, 2026

### ⚠️ Important Notice for v1 Users

**YokeFlow v2.1.0 requires a completely fresh database installation.** The database schema has been significantly restructured and consolidated:

- ✅ **Removed**: 17 unused tables from incomplete implementations
- ✅ **Added**: 5 new quality system tables (migrations 017-020)
- ✅ **Cleaned**: All obsolete objects and references removed
- ✅ **Consolidated**: Single clean schema file (schema.sql v2.1.0)

**Migration from v1 is not supported.** All existing projects and data will be lost.

---

## Fresh Installation Instructions

### Step 1: Backup Any Important Data (Optional)

If you have any projects you want to preserve from v1:

```bash
# Export project names and specs (manual backup)
# Copy any important app_spec.txt files from projects/ folder
cp -r projects/ ~/yokeflow-v1-backup/
```

### Step 2: Remove Old Database

```bash
# Stop all YokeFlow services
docker-compose down -v

# This removes all volumes including the database
# All projects and data will be deleted
```

### Step 3: Install Fresh Database

```bash
# Start PostgreSQL container
docker-compose up -d postgres

# Wait for PostgreSQL to be ready (5-10 seconds)
sleep 10

# Initialize with v2.1.0 schema
python scripts/init_database.py --docker
```

### Step 4: Verify Installation

```bash
# Check database has correct number of tables (should be 19)
docker exec yokeflow_postgres psql -U agent -d yokeflow -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"

# Check views (should be ~27)
docker exec yokeflow_postgres psql -U agent -d yokeflow -c "SELECT COUNT(*) FROM information_schema.views WHERE table_schema = 'public';"
```

### Step 5: Rebuild MCP Server

```bash
cd mcp-task-manager
npm run build
cd ..
```

### Step 6: Start All Services

```bash
# Start all services
docker-compose up -d

# Or start API and Web UI manually
uvicorn server.api.app:app --host 0.0.0.0 --port 8010 --reload &
cd web-ui && npm run dev &
```

---

## What's New in v2.1.0

### Quality System Features

1. **Test Error Tracking** (Migration 017)
   - Tracks error messages, execution times, retry counts
   - Identifies slow and flaky tests

2. **Epic Test Failure Analysis** (Migration 018)
   - Comprehensive failure history with 22 fields
   - Automatic flaky test detection
   - Pattern analysis for quality improvements

3. **Epic Re-testing System** (Migration 019)
   - Automatic regression detection
   - Stability scoring (0.00-1.00 scale)
   - Smart re-test scheduling

4. **Project Completion Reviews** (Migration 020)
   - Validates projects against original specifications
   - Requirement matching with 70-85% accuracy
   - Coverage scoring and recommendations

### Database Improvements

- **Clean Schema**: Removed 865 lines of obsolete definitions
- **19 Tables**: Down from 49 (consolidated and cleaned)
- **27 Views**: Down from 37 (removed unused views)
- **17 Functions**: Streamlined and optimized
- **Accurate Documentation**: schema.sql matches actual database

---

## Troubleshooting

### Database Won't Initialize

```bash
# Check PostgreSQL logs
docker logs yokeflow_postgres

# Verify PostgreSQL is ready
docker exec yokeflow_postgres pg_isready

# Try reinitializing
docker-compose down -v
docker-compose up -d postgres
sleep 10
python scripts/init_database.py --docker
```

### MCP Server Build Fails

```bash
# Clean and rebuild
cd mcp-task-manager
rm -rf node_modules dist
npm install
npm run build
```

### Tables Missing After Installation

```bash
# Verify init script ran successfully
python scripts/init_database.py --docker

# Check for error messages in output
# If errors occurred, check DATABASE_URL in .env file
```

---

## Why Fresh Installation?

The v2.1.0 release includes:

1. **Schema Consolidation**: Removed 34 unused database objects from failed experiments
2. **Quality System Integration**: 5 new tables for comprehensive quality tracking
3. **Breaking Changes**: Column additions to existing tables (task_tests, epic_tests)
4. **Index Optimization**: New indexes for performance
5. **View Updates**: 13 new quality-focused views

These changes are too extensive for a migration script. A fresh installation ensures:
- ✅ Clean database without legacy artifacts
- ✅ Optimal performance with new indexes
- ✅ Correct schema matching documentation
- ✅ No orphaned references or conflicts

---

## Questions or Issues?

1. **Check Documentation**: See [QUALITY_SYSTEM_SUMMARY.md](QUALITY_SYSTEM_SUMMARY.md) for feature details

---

**Last Updated**: February 2, 2026
**Schema Version**: 2.1.0
**Migration Status**: ⚠️ Fresh installation required (no migration path from v1)

