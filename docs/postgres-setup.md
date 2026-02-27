# PostgreSQL Setup Guide

This guide walks through setting up PostgreSQL for the YokeFlow platform.

## Quick Start (Local Development with Docker)

### 1. Start PostgreSQL with Docker Compose

```bash
# Start PostgreSQL container
docker-compose up -d

# Verify it's running
docker-compose ps

# Check logs if needed
docker-compose logs postgres
```

The database will be available at:
- **Host**: localhost
- **Port**: 5432
- **Database**: yokeflow
- **Username**: agent
- **Password**: agent_dev_password

### 2. Initialize the Database Schema

```bash
# Install Python dependencies first
pip install -r requirements.txt

# Initialize database with schema
python scripts/init_database.py --docker

# Or if you want to verify existing schema
python scripts/init_database.py --docker --verify-only
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
# The default DATABASE_URL is already configured for Docker
```

### 4. Optional: Access pgAdmin

If you want a GUI to manage the database:

```bash
# Start pgAdmin (runs on http://localhost:5050)
docker-compose --profile tools up -d

# Login credentials:
# Email: admin@yokeflow.local
# Password: admin
```

## Production Setup (Digital Ocean)

### 1. Create Managed Database

1. Log into Digital Ocean
2. Create a new PostgreSQL database cluster
3. Note the connection parameters

### 2. Configure Connection

Update your `.env` file:

```bash
DATABASE_URL=postgresql://username:password@host:port/database?sslmode=require
```

### 3. Initialize Schema

```bash
# Run initialization with production URL
python scripts/init_database.py --url "$DATABASE_URL"
```

## Database Management

### Connect with psql

```bash
# Local Docker
docker exec -it yokeflow-postgres psql -U agent -d yokeflow

# Production
psql "$DATABASE_URL"
```

### Common SQL Commands

```sql
-- View all tables
\dt

-- View table structure
\d projects

-- View custom types
\dT

-- View all views
\dv

-- Check project progress
SELECT * FROM v_progress;

-- Get active sessions
SELECT * FROM v_active_sessions;

-- Exit psql
\q
```

### Backup and Restore

```bash
# Backup
docker exec yokeflow-postgres pg_dump -U agent yokeflow > backup.sql

# Restore
docker exec -i yokeflow-postgres psql -U agent yokeflow < backup.sql
```

## Troubleshooting

### Port 5432 Already in Use

If you have another PostgreSQL running:

```bash
# Change port in docker-compose.yml
ports:
  - "5433:5432"  # Use port 5433 instead

# Update DATABASE_URL in .env
DATABASE_URL=postgresql://agent:agent_dev_password@localhost:5433/yokeflow
```

### Connection Refused

```bash
# Check if container is running
docker-compose ps

# Check logs
docker-compose logs postgres

# Restart container
docker-compose restart postgres
```

### Permission Denied

```bash
# Ensure schema files have correct permissions
chmod +r schema/postgresql/*.sql

# Rebuild container if needed
docker-compose down
docker-compose up -d
```

## Database Schema Overview

The PostgreSQL schema includes:

### Main Tables (Core Schema)
- **projects**: Central project metadata
- **sessions**: Agent session tracking
- **epics**: High-level feature areas
- **tasks**: Implementation steps
- **tests**: Verification steps
- **reviews**: Quality tracking
- **github_commits**: Git integration
- **project_preferences**: Per-project settings

### Production Hardening Tables (v1.4.0+)
- **session_checkpoints**: Recovery system (schema 012)

### Verification System Tables (v2.0+)
- **task_verifications**: Task testing results (schema 016)
- **epic_validations**: Epic integration tests (schema 016)
- **generated_tests**: Test catalog (schema 016)
- **verification_history**: Audit trail (schema 016)

### Custom Types (ENUMs)
- `project_status`: active, paused, completed, archived
- `session_type`: initializer, coding, review
- `session_status`: pending, running, completed, error, interrupted
- `task_status`: pending, in_progress, completed, blocked

### Key Features
- UUID primary keys for distributed systems
- JSONB fields for flexible metadata
- PostgreSQL arrays for task lists
- Generated columns for computed values
- GIN indexes for JSON performance
- Triggers for auto-updating timestamps

## Database Migration Files

The schema directory contains the base schema and migration files:

**Base Schema**:
- `schema/postgresql/schema.sql` - Complete base schema for fresh installations

**Migration Files** (apply in order if upgrading from v1.0-v1.4):
- `012_session_checkpoints.sql` - Checkpoint recovery (v1.4.0)
- `013_task_verification.sql` - Task verification (v2.0)
- `014_epic_validation.sql` - Epic validation (v2.0)
- `015_quality_gates.sql` - Quality gates (v2.0)
- `016_verification_system.sql` - Complete verification framework (v2.0)

**Fresh Install (Recommended)**:
```bash
# For new installations, use schema.sql which includes all features
python scripts/init_database.py
```

**Upgrade from v1.4**:
```bash
# Apply only the new verification system migration
psql $DATABASE_URL < schema/postgresql/016_verification_system.sql
```

**Note**: YokeFlow v2.0 requires a fresh installation. Migration from v1.x is not supported.

## Migration Status

✅ **v2.0 Complete**

All v2.0 features have been completed:
1. ✅ PostgreSQL configuration and connection layer
2. ✅ Orchestrator migration with async/await
3. ✅ REST API migration with all endpoints
4. ✅ Project structure changes (reorganized under `server/`)
5. ✅ Integration testing and validation (70% coverage)
6. ✅ Code consolidation (removed all `_pg` duplicate files)
7. ✅ Production hardening (retry logic, intervention, checkpointing)
8. ✅ Verification system (automatic task testing)

The codebase is now **PostgreSQL-only** with no SQLite dependencies remaining.

## Current Architecture (v2.0)

- `server/database/operations.py` - PostgreSQL database layer (asyncpg)
- `server/database/connection.py` - Connection pooling and lifecycle
- `server/database/retry.py` - Retry logic with exponential backoff
- `server/agent/orchestrator.py` - Async session management
- `server/api/app.py` - FastAPI with PostgreSQL backend
- UUID-based project identification
- JSONB for flexible metadata
- Connection pooling (10-20 connections)
- Production hardening (retry logic, intervention system, checkpointing)

## Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Digital Ocean Managed Databases](https://www.digitalocean.com/products/managed-databases)