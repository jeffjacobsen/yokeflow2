# 🚨 BREAKING CHANGE - Fresh Installation Required

**YokeFlow v2.4.0 requires a completely fresh database installation.** The database schema has been significantly restructured and consolidated:

**Migration from earlier versions is not supported.** All existing projects and data will be lost.

---

## Fresh Installation Instructions

### Step 1: Remove Old Database

```bash
# Stop all YokeFlow services
docker-compose down -v

# This removes all volumes including the database
# All projects and data will be deleted
```

### Step 2: Install Fresh Database

```bash
# Start PostgreSQL container
docker-compose up -d postgres

# Wait for PostgreSQL to be ready (5-10 seconds)
sleep 10

# Initialize with v2.1.0 schema
python scripts/init_database.py --docker
```

### Step 3: Rebuild MCP Server

```bash
cd mcp-task-manager
npm run build
cd ..
```


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

