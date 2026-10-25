# Deploying AdOps360 to a single EC2 instance

This guide covers the production composition (`docker-compose.prod.yml`) and the steps that cannot be run or tested from a development machine. What can be checked locally is checked by `scripts/verify_prod_images.sh`, which builds the images and starts the production composition with throwaway settings and a self-signed certificate.

Nothing secret lives in the repository: not the `.env`, not the certificates and not their keys.

## 1. Prerequisites

- An AWS account with a Cognito User Pool and an app client (authorization code + PKCE, no client secret).
- A domain name you control (`SERVER_NAME` below, e.g. `adops.example.com`).
- An S3 bucket and, for ingestion, the DSP credentials (Adform first).

## 2. The instance

1. Launch an Ubuntu LTS instance (t3.small or t3.medium) and attach an Elastic IP, so DNS does not change on a restart.
2. Install Docker Engine and the Compose plugin from Docker's repository.
3. Add the deploy user to the `docker` group, clone the repository and check out the release branch.

## 3. Security group

| Port | Source | Why |
|---|---|---|
| 22 | Your office or VPN address only | SSH |
| 80 | 0.0.0.0/0 | Redirect to HTTPS and the Certbot challenge |
| 443 | 0.0.0.0/0 | The application |

PostgreSQL (5432), the backend (8000) and the frontend (3000) are never opened. The production composition does not publish them either: only nginx publishes ports.

## 4. DNS

Create an `A` record for `SERVER_NAME` pointing to the Elastic IP, and wait until it resolves from outside before asking for a certificate.

## 5. Cognito

In the app client of the User Pool, set over HTTPS:

- Allowed callback URL: `https://<SERVER_NAME>/callback`
- Allowed sign-out URL: `https://<SERVER_NAME>/`

Remove the `http://localhost` URLs from the production client. Cognito only accepts HTTP for localhost, so a client that still lists other HTTP URLs is a configuration error.

## 6. The `.env` file

```
cp .env.example .env
chmod 600 .env
```

Edit it and replace every example value. Besides the usual variables, set:

- `SERVER_NAME`: the host name, without scheme (`adops.example.com`).
- `NEXT_PUBLIC_API_URL`: `https://<SERVER_NAME>/api`.
- `COGNITO_DOMAIN`: the hosted UI domain, without `https://`.
- `NEXT_PUBLIC_MASK_NAMES` (optional): with the exact value `true`, every Adform campaign and line name is drawn blurred, cannot be selected and does not reveal on hover, which is useful for screenshots and demos. Leave it empty to show names normally. It is a build variable like the other `NEXT_PUBLIC_*` ones.

`NEXT_PUBLIC_*` values and `COGNITO_DOMAIN` are inlined into the browser bundle when the frontend image is built, so changing them requires rebuilding that image. Only the public settings reach the frontend build; the DSP credentials never do. Never commit `.env`, and do not paste it in tickets or chats.

## 7. The first certificate

nginx refuses to start without its certificate, so the first one is requested before nginx is up, with Certbot answering on port 80 by itself:

```
docker compose -f docker-compose.prod.yml run --rm -p 80:80 certbot certonly --standalone \
  -d <SERVER_NAME> --email <you@example.com> --agree-tos --no-eff-email
```

The certificate lands in the `certbot_certs` volume, where nginx reads it (`/etc/letsencrypt/live/<SERVER_NAME>/`).

Renewal (certificates last 90 days). Run it from cron on the host, for example weekly; it only renews when the certificate is close to expiry, and it stops nginx for a few seconds so Certbot can use port 80:

```
docker compose -f docker-compose.prod.yml stop nginx
docker compose -f docker-compose.prod.yml run --rm -p 80:80 certbot renew --standalone
docker compose -f docker-compose.prod.yml up -d nginx
```

## 8. Start the stack

```
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --wait
```

## 9. Migrations (an explicit step)

The backend never migrates when it starts. After the first start, and after every release that adds a migration:

```
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

Back up the `postgres_data` volume before a release that includes migrations.

## 10. Master data

A fresh database has no agencies, advertisers, DSPs, channels, formats, campaign types, sectors or sales reps, and the "new campaign" form needs them. Load them from a JSON file with `scripts/load_masters.py`. Start from the template, which holds fictitious data:

```
cp deploy/masters.example.json deploy/masters.json
chmod 644 deploy/masters.json
```

`deploy/masters.json` is ignored by git; the backend container runs as another user, which is why the file must be readable by others (it holds business names, not secrets). Edit it. Each section is a list of objects with a mandatory `name`; an agency also has a mandatory `holding_group` (the name of its group); a DSP may have `is_active` (true unless you say otherwise). Nothing else is accepted, and a misspelled section or key is an error.

The file must keep a DSP named `Adform`, because the ingestion looks it up (it may already be stored from an earlier load). Every agency must name a group defined in the same file or already stored.

Validate first, then load. The file is mounted read-only, since the image does not carry it:

```
docker compose -f docker-compose.prod.yml run --rm \
  -v "$PWD/deploy/masters.json:/tmp/masters.json:ro" \
  backend python -m scripts.load_masters /tmp/masters.json --check

docker compose -f docker-compose.prod.yml run --rm \
  -v "$PWD/deploy/masters.json:/tmp/masters.json:ro" \
  backend python -m scripts.load_masters /tmp/masters.json
```

The output is counts per table (`created`, or `would create` with `--check`, and `existing`) and never a name. A problem in the file is reported by section and position, for example `agencies[2]: the holding group is neither in the file nor stored`. Exit code 0 means done, 1 the database failed, 2 the file or the arguments are invalid, 3 `DATABASE_URL` is missing.

It is safe to run again, for example after adding an agency to the file: items are identified by name, new ones are created and existing ones are left exactly as they are. It never modifies or deletes: renaming a master, moving an agency to another group or changing a DSP's `is_active` is not done by this command. The load is a single transaction, so a failure stores nothing.

## 11. The first user

The development seed is not in the production image. Create the first user, with the roles you need, with:

```
docker compose -f docker-compose.prod.yml run --rm backend \
  python -m scripts.grant_roles <email> operations [business] [finance]
```

Use the email Cognito puts in the token, spelled exactly the same: it is the only link between Cognito and the local user. The command creates the user if it does not exist, creates the requested role rows if they are missing, and prints counts only. Running it again changes nothing.

## 12. Nightly ingestion

The ingestion is a command for the host scheduler, not a container. It needs the Adform credentials in `.env`. Run it once by hand and look at its output before scheduling it:

```
docker compose -f docker-compose.prod.yml run --rm backend python -m scripts.run_ingestion
```

It prints states and counts only, never an identifier, a name, an amount or a token:

```
status: succeeded
rows_read: ...
ignored_rows: ...
zero_unmatched_rows: ...
new_exceptions: ...
skipped_lines: ...
absences: ...
```

Exit codes: 0 succeeded, 1 failed (the line `error:` names the class of the error), 2 another run holds the lock, 3 configuration is missing. Reconcile the first figures by hand against Adform before scheduling it.

### The schedule: 07:00 Madrid time

Schedule it at **07:00 Europe/Madrid, not shortly after midnight**: Adform restates figures during the early hours, and a run at midnight would store figures that are then superseded. The command ingests the window D-7 to D-1 in the zone set by `APP_TIMEZONE` (Europe/Madrid by default), so the cron zone and that setting should agree.

On the host, as the deploy user (`crontab -e`), with the repository in `/opt/adops360` and the log directory created beforehand (`sudo mkdir -p /var/log/adops360 && sudo chown $USER /var/log/adops360`):

```
CRON_TZ=Europe/Madrid
0 7 * * * cd /opt/adops360 && /usr/bin/docker compose -f docker-compose.prod.yml run --rm -T backend python -m scripts.run_ingestion >> /var/log/adops360/ingestion.log 2>&1; echo "$(date -Is) exit=$?" >> /var/log/adops360/ingestion.log
```

- `CRON_TZ` applies to the lines after it and makes the time Madrid's whatever the clock of the instance is, daylight saving included. The cron on Ubuntu and Debian supports it (`man 5 crontab`); check that yours does before relying on it.
- `-T` is required, because cron has no terminal; the absolute path to `docker` is required, because cron's `PATH` is minimal.
- The `echo` after the `;` records the exit code of the run next to its output.

### Checking the exit code

Every morning, or from a monitor, look at the last line the job wrote:

```
tail -n 9 /var/log/adops360/ingestion.log
grep 'exit=' /var/log/adops360/ingestion.log | tail -n 3
```

`exit=0` is a good run. Anything else needs a look: `exit=1` read the `error:` line, `exit=2` find out what held the lock (a manual run left open, or a previous run still going), `exit=3` the configuration of `.env` is incomplete. A day without an `exit=` line means the job did not run (cron stopped, instance down). Re-running a day is safe: the window is idempotent, so `run_ingestion` can be repeated by hand (`--date YYYY-MM-DD` repeats a given day's window).

## 13. Backups

The data lives in the `postgres_data` volume, so losing the instance's disk loses everything. Take a nightly `pg_dump` from inside the database container, keep seven days of them and prove a restore from time to time. This is documentation: none of it is installed by the repository.

### The nightly dump

Save as `/opt/adops360/backup.sh` (`chmod 700`), owned by the deploy user:

```
#!/bin/sh
set -eu
cd /opt/adops360
BACKUP_DIR=/var/backups/adops360
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
STAMP=$(date +%F)

# Custom format: compressed, and pg_restore can pick what to restore. Written to a temporary name so a
# failed dump never replaces a good file.
/usr/bin/docker compose -f docker-compose.prod.yml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$BACKUP_DIR/adops360-$STAMP.dump.tmp"
mv "$BACKUP_DIR/adops360-$STAMP.dump.tmp" "$BACKUP_DIR/adops360-$STAMP.dump"

# Rotation: keep seven days (today and the six before).
find "$BACKUP_DIR" -name 'adops360-*.dump' -mtime +6 -delete
```

`$POSTGRES_USER` and `$POSTGRES_DB` are read inside the container, from the `.env` it was started with, so the script holds no credential. In the crontab, before the ingestion (after the `CRON_TZ` line):

```
30 3 * * * /opt/adops360/backup.sh >> /var/log/adops360/backup.log 2>&1; echo "$(date -Is) exit=$?" >> /var/log/adops360/backup.log
```

A dump on the same disk does not survive losing that disk. Copy `/var/backups/adops360` off the instance as well (for example to an S3 bucket with lifecycle rules, using an instance role and not keys in `.env`).

### Testing a restore, in a temporary database

Do this after setting up the backup, and then every month. It restores the latest dump into a throwaway database next to the real one and never touches the real one:

```
LATEST=$(ls -1 /var/backups/adops360/adops360-*.dump | tail -n 1)

docker compose -f docker-compose.prod.yml exec -T db sh -c 'createdb -U "$POSTGRES_USER" restore_test'
docker compose -f docker-compose.prod.yml exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d restore_test --no-owner' < "$LATEST"

# The restored copy is at the same migration as the real database and has the data.
docker compose -f docker-compose.prod.yml exec -T db sh -c 'psql -U "$POSTGRES_USER" -d restore_test -tAc "select version_num from alembic_version"'
docker compose -f docker-compose.prod.yml exec -T db sh -c 'psql -U "$POSTGRES_USER" -d restore_test -tAc "select count(*) from campaigns"'

docker compose -f docker-compose.prod.yml exec -T db sh -c 'dropdb -U "$POSTGRES_USER" restore_test'
```

The test passes if `pg_restore` ends without errors, the version equals the output of `alembic current` on the real database, and the count is plausible. Always drop `restore_test` afterwards.

To recover for real: stop `backend`, restore into an empty database (never over a live one), start `backend` again and check section 14.

## 14. Checking a deployment

Right after the first deployment and after every release:

- `curl -fsS https://<SERVER_NAME>/api/health` answers 200.
- `curl -sI http://<SERVER_NAME>/` answers 301 to HTTPS.
- `docker compose -f docker-compose.prod.yml ps` shows every service as healthy.
- From outside, `nmap` of the instance shows only 22, 80 and 443.
- `docker compose -f docker-compose.prod.yml run --rm backend alembic current` ends in `(head)`.

### An authenticated request

The status endpoint is the end-to-end check: it needs a valid Cognito token, the user's roles in the database and the migrated schema.

Without a token it must answer 401:

```
curl -s -o /dev/null -w '%{http_code}\n' https://<SERVER_NAME>/api/campaign-status
```

With a token, sign in to the application with the first user (section 11), open the browser's developer tools, and copy the `Authorization: Bearer ...` value of any request to `/api/`. Read it into a shell variable without echoing it or leaving it in the history, and use it once:

```
read -rs ID_TOKEN
curl -fsS -H "Authorization: Bearer $ID_TOKEN" https://<SERVER_NAME>/api/campaign-status
unset ID_TOKEN
```

On a fresh database the answer is `200` with `[]` (no campaign is running yet). `401` means the token is not accepted (check the `COGNITO_*` values in `.env` against the pool, and that the token is the ID token), `403` means the email in the token has no user or no `operations` or `business` role (section 11). The same in the browser: the "Estado" page shows "No hay campañas en curso" rather than an error.

### The ingestion

Run the command once by hand (section 12) and check that its output starts with `status: succeeded` and that the exit code is 0:

```
docker compose -f docker-compose.prod.yml run --rm backend python -m scripts.run_ingestion; echo "exit=$?"
```

Once campaigns and their DSP mappings exist, the "Excepciones" page lists what a run could not place.

## 15. Logs and restarts

Every service rotates its logs (`json-file`, 10 MB by 5 files) and restarts unless stopped by hand, including after a reboot of the instance.
