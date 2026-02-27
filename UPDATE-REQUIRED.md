# Fresh Database Required

If you have an existing YokeFlow database from an earlier version, it must be replaced. The schema has been restructured and migration from earlier versions is not supported.

## Steps

```bash
# Stop services and remove old database volume
docker compose down -v

# Start fresh PostgreSQL
docker compose up -d

# Wait for PostgreSQL to be ready
sleep 10

# Initialize schema
python scripts/init_database.py --docker
```

## Troubleshooting

If the database won't initialize:

```bash
# Check PostgreSQL logs
docker logs yokeflow_postgres

# Verify PostgreSQL is ready
docker exec yokeflow_postgres pg_isready

# Retry from scratch
docker compose down -v
docker compose up -d
sleep 10
python scripts/init_database.py --docker
```
