#!/bin/sh
# Nightly database dumps, run by the `backup` service in docker-compose.prod.yml.
#
# Once a day at HR_BACKUP_HOUR (UTC) this writes a compressed, custom-format dump
# to /backups, verifies it can be listed, and deletes dumps older than
# HR_BACKUP_KEEP_DAYS. Copy /backups off the host too: a backup on the same disk
# as the database does not survive that disk.
#
# Restore with deploy/restore.sh, and test a restore before you need one.
set -eu

HOUR="${HR_BACKUP_HOUR:-2}"
KEEP="${HR_BACKUP_KEEP_DAYS:-14}"

dump() {
  stamp="$(date -u +%Y%m%d-%H%M)"
  tmp="/backups/.halverson-$stamp.dump.partial"
  out="/backups/halverson-$stamp.dump"
  echo "backup: dumping to $out"
  pg_dump --format=custom --compress=6 --no-owner --file="$tmp"
  # A dump that cannot be listed would not restore either.
  pg_restore --list "$tmp" > /dev/null
  mv "$tmp" "$out"
  find /backups -name 'halverson-*.dump' -mtime +"$KEEP" -print -delete
  echo "backup: done ($(du -h "$out" | cut -f1))"
}

last=""
while true; do
  today="$(date -u +%Y-%m-%d)"
  now_hour="$(date -u +%H | sed 's/^0//')"
  if [ "$today" != "$last" ] && [ "${now_hour:-0}" -ge "$HOUR" ]; then
    if dump; then last="$today"; else echo "backup: FAILED, retrying in 10 minutes" >&2; fi
  fi
  sleep 600
done
