#!/bin/sh
# Restore a dump written by deploy/backup.sh.
#
#   deploy/restore.sh backups/halverson-20260912-0200.dump
#
# This REPLACES the database. It stops the API and worker, restores into the
# running `db` service, runs migrations (so an older dump is brought up to the
# current code), then starts everything again. Rehearse it on a copy first.
set -eu

dump="${1:?usage: deploy/restore.sh path/to/halverson-YYYYmmdd-HHMM.dump}"
compose="docker compose -f docker-compose.prod.yml --env-file deploy/.env"

[ -f "$dump" ] || { echo "No such file: $dump" >&2; exit 1; }
printf 'This replaces the database with %s. Type "restore" to continue: ' "$dump"
read -r answer
[ "$answer" = "restore" ] || { echo "Nothing changed."; exit 1; }

$compose stop api worker
$compose exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$dump"
$compose run --rm migrate
$compose start api worker
echo "Restored $dump."
