# Deploying AdOps360 to a single EC2 instance

This guide covers the production composition (`docker-compose.prod.yml`) and the steps that cannot be run or tested from a development machine. What can be checked locally is checked by `scripts/verify_prod_images.sh`, which builds the images and starts the production composition with throwaway settings and a self-signed certificate.

Nothing secret lives in the repository: not the `.env`, not the certificates and not their keys.

## The `btree_gist` extension

The margin migration creates the PostgreSQL extension `btree_gist`, which the exclusion constraint on rebate schedules needs. The database user that runs migrations must be allowed to create extensions: the PostgreSQL superuser of the Compose `db` container is. On a database where that is not allowed, an administrator must run `CREATE EXTENSION btree_gist;` before the migration; otherwise the migration stops with a message saying so. Its downgrade removes the extension only if the migration was the one that created it.

## 1. Prerequisites

- A Microsoft Entra ID tenant (the company's) where you can register an application, and the users who will sign in. Production has its own registration, separate from the development one (section 5).
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

## 5. Microsoft Entra ID

Microsoft Entra ID is the only identity provider. Register an application for production in the company tenant, separate from the development registration (which lists `http://localhost` URIs), with:

- **Supported account types:** this organisational directory only (single tenant).
- **Platform:** single-page application (SPA), with the redirect URI `https://<SERVER_NAME>/callback` and the post-logout redirect URI `https://<SERVER_NAME>`. The browser uses the authorization code flow with PKCE, with no client secret.
- **Expose an API:** the application ID URI `api://<client-id>` and a delegated scope named `access_as_user`. The browser asks for `api://<client-id>/access_as_user` besides `openid profile email`, and the backend rejects any token without that scope.
- **Access token version 2:** in the manifest, `requestedAccessTokenVersion: 2`. The backend rejects any other version, and the audience of a version 2 token is the client id itself.
- **The optional claim `email` in the access token, which is required here.** The first access of a user finds them by that claim and stores their link (section 11), and no tool links a user in advance. Without it the first access cannot be linked: a user who is not linked yet is answered 403 `user_not_registered`.
- **Assignment required:** in the enterprise application, set *Assignment required* to yes and assign the users who may sign in. Being assigned only lets a person sign in; what they may do still comes from their roles in the database.
- **No application roles.** A `roles` claim in the token is ignored: roles live only in the database.

The tenant id and the client id go into `.env` (section 6) and nowhere else: never in the repository, a ticket or a chat.

## 6. The `.env` file

```
cp .env.example .env
chmod 600 .env
```

Edit it and replace every example value. Besides the usual variables, set:

- `SERVER_NAME`: the host name, without scheme (`adops.example.com`).
- `NEXT_PUBLIC_API_URL`: `https://<SERVER_NAME>/api`.
- `ENTRA_TENANT_ID` (`<tenant-id>`) and `ENTRA_CLIENT_ID` (`<client-id>` of the production registration). Both are required: without either of them every `docker compose` command stops with `required variable ENTRA_TENANT_ID is missing a value` (or the client one), and the backend refuses to start. Compose also passes them to the frontend build as `NEXT_PUBLIC_ENTRA_TENANT_ID` and `NEXT_PUBLIC_ENTRA_CLIENT_ID`; you do not write those yourself.
- `EQUATIV_CLIENT_ID` and `EQUATIV_CLIENT_SECRET`: the credentials of the Equativ API, **only in this `.env`**, with `chmod 600`, never in the repository, a ticket or a chat. The API does not need them (mapping a Deal line never asks Equativ, section 12); only `run_ingestion --dsp Equativ` does, and without them it stops with `status: not configured` and exit code 3. A container keeps the environment it was created with: after adding or changing them, recreate the backend (`docker compose -f docker-compose.prod.yml up -d --force-recreate backend`), or a command run with `exec` in it will not receive them. A `run --rm`, as the cron of section 12 uses, starts a new container and reads them.
- `NEXT_PUBLIC_MASK_NAMES` (optional): with the exact value `true`, every Adform campaign and line name is drawn blurred, cannot be selected and does not reveal on hover, which is useful for screenshots and demos. Leave it empty to show names normally. It is a build variable like the other `NEXT_PUBLIC_*` ones: it is inlined when the frontend image is built, so changing it means rebuilding that image. It only blurs the names visually. The names are still in the page's data and in the API responses, so it is **not a guarantee of confidentiality** on a published page: do not rely on it to keep the names from anyone who can open the application.

`NEXT_PUBLIC_*` values, including the two Entra ones derived from `ENTRA_*`, are inlined into the browser bundle when the frontend image is built, so changing them requires rebuilding that image. The production build of the frontend fails, naming the variable, when `NEXT_PUBLIC_ENTRA_TENANT_ID` or `NEXT_PUBLIC_ENTRA_CLIENT_ID` is empty, instead of failing in the browser. Only the public settings reach the frontend build; the DSP credentials never do. Never commit `.env`, and do not paste it in tickets or chats.

### No test issuer in production

The test issuer of development and the end-to-end tests (`TEST_ISSUER_PUBLIC_KEY_FILE`, `scripts/generate_test_issuer_keys.sh`) has no place on the instance: do not generate its keys there and do not set the variable. `docker-compose.prod.yml` sets `APP_ENV=production` under `environment:`, which `.env` cannot override, and mounts no key. The backend fails closed: with the key set and `APP_ENV` anything but `development` or `test`, it refuses to start.

`scripts/verify_prod_images.sh` checks this locally, among the rest: it builds the production images and starts the production composition with throwaway settings and a self-signed certificate, and checks that `/api/health` answers 200 over HTTPS, that port 80 redirects, that the backend image carries no tests, development seeds or private key and does not run as root, that the backend refuses to start with the test issuer key, that the database is not published, and that the migrations are a separate step.

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

The Compose project is named `adops360` by `docker-compose.prod.yml` itself (`name: adops360`), not by the folder the repository is cloned into: `/opt/adops360` is only the path used in the examples of this guide. Its volumes are therefore `adops360_postgres_data`, `adops360_certbot_certs` and `adops360_certbot_webroot` wherever the repository lives. Do not set `COMPOSE_PROJECT_NAME` on the instance and do not pass `-p`: either would rename the project, and the stack would start with new, empty volumes next to the real ones.

## 9. Migrations (an explicit step)

The backend never migrates when it starts. After the first start, and after every release that adds a migration:

```
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

Back up the `postgres_data` volume before a release that includes migrations.

### The release that adds the OTS columns and the channel's delivery metric (`ctv-and-delivery-metric`)

This release adds two migrations: one gives `daily_deliveries` the columns `ots` and `video_completions`, and the next gives `channels` its `delivery_metric` and sets `ots` on the channel named `DOOH`. Deploying it over a database that already has data needs one more step, **before the first detection of lines without delivery after the deploy** (the nightly run does that detection, so before the first nightly run that follows the deploy, or with the schedule stopped until this is done):

1. Re-ingest the range of the DOOH flights that have already ended, so that `ots` is filled in (§12, *Loading a history range*, in blocks of at most 31 days). Rows stored before the column existed read 0 OTS, and a range run does not run the check for lines without delivery.
2. Then let the nightly ingestion run as usual.

If it is not done, a finished DOOH flight whose delivery all predates the column reads 0 OTS and is reported as a line without delivery. **Those exceptions are false, and they do not close by themselves:** the exception queue never closes or reopens an exception when delivery appears later, so operations have to resolve each one by hand. The same rows also show 0 delivered OTS in the status and the margin until they are re-ingested, though the revenue and the platform cost do not change.

### The release that freezes a closed month (`closing-snapshot`)

This release adds one migration, `3a08cce1c979`, which creates the closing headers (`month_closings`, `month_closing_batches`) and the snapshot of every closed flight (`closed_flight_snapshots`). It **refuses a database whose `applied_rates` holds any row**: the snapshot of a flight closed before it cannot be rebuilt, because the delivery the flight was closed with is no longer stored, and the migration does not backfill it. The refusal leaves the database as it was, and its message names `e2e/scripts/reset-data.sh`.

There is no production database yet, so a new installation migrates as usual. A development database with closed months is rebuilt with `e2e/scripts/reset-data.sh`, which drops the volume, migrates and seeds again. A database holding real closed months would need a backfill of its own before this migration.

## 10. Master data

A fresh database has no agencies, advertisers, DSPs, channels, formats, campaign types, sectors or sales reps, and the "new campaign" form needs them. Load them from a JSON file with `scripts/load_masters.py`. Start from the template, which holds fictitious data:

```
cp deploy/masters.example.json deploy/masters.json
chmod 644 deploy/masters.json
```

`deploy/masters.json` is ignored by git; the backend container runs as another user, which is why the file must be readable by others (it holds business names, not secrets). Edit it. Each section is a list of objects with a mandatory `name`; an agency also has a mandatory `holding_group` (the name of its group); a DSP may have `is_active` (true unless you say otherwise); a channel may have `delivery_metric`, `impressions` (the default) or `ots`, the unit in which the contracted and the delivered volume of its lines are counted (the template gives `DOOH` `ots` and the other three channels `impressions`). Nothing else is accepted, and a misspelled section or key is an error.

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

### A channel's delivery metric

The load never changes the metric of a channel that exists. A file that names an existing channel with a different `delivery_metric` is rejected as a whole and nothing is written, with `--check` too; the output names the position and never the value, for example `channels[1]: the delivery metric differs from the stored one`. Leaving the key out, or repeating the stored value, is fine, and a channel the file creates takes the metric the file gives it.

**Changing the metric of an existing channel is not supported.** `load_masters` refuses it and the application has no route for it. If it is ever needed, it goes in a reviewed migration, never in a manual change to the database: it changes the meaning of the contracted volume of every campaign of that channel, and of everything computed from it (the delivered volume, the pacing, the margin and the check for lines without delivery), while the stored delivery is not converted. The database itself accepts only `impressions` and `ots`. A campaign's lines must share one metric, so a campaign that mixes `DOOH` with another channel is refused at registration.

## 11. The first user

The development seed is not in the production image. Create the first user, with the roles you need, with:

```
docker compose -f docker-compose.prod.yml run --rm backend \
  python -m scripts.grant_roles <email> operations [business] [finance] [trading]
```

Use the email Entra puts in the `email` claim of the user's access token, spelled the same (the comparison ignores case). Signing in never creates a user: the first access finds the registered user by that email and stores the pair (issuer, `oid`), and from then on only the pair counts, even if the email changes in Entra. A user has a single identity: an email that matches a user already linked to another pair is answered 403 `identity_link_conflict`. The user must also be assigned to the production application (section 5). The command creates the user if it does not exist, creates the requested role rows if they are missing, and prints counts only. Running it again changes nothing.

To deactivate or reactivate a user later, an operations user calls `POST /api/users/activation`; whoever administers the database can run `python -m scripts.set_user_active --email <email> --inactive` (or `--active`), which has none of the endpoint's lock-out protections. Either takes effect on the user's next request.

## 12. Nightly ingestion

The ingestion is a command for the host scheduler, not a container. It ingests one DSP per run, chosen with `--dsp` (`Adform` by default, or `Equativ`), and needs that DSP's credentials in `.env`. Each DSP has its own lock, so an Adform run and an Equativ run can overlap. Run it once by hand and look at its output before scheduling it:

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
mapped_lines: ...
skipped_lines: ...
absences: ...
closed_month_days: ...
```

Exit codes: 0 succeeded, 1 failed (the line `error:` names the class of the error), 2 another run holds the lock, 3 configuration is missing. Reconcile the first figures by hand against Adform before scheduling it.

`closed_month_days` is how many days of the run's window fall in a closed month (one that holds a closing header). Those days are ingested like any other: the figures of a closed month never move, and a closed flight whose delivery changed only gets the warning «Cambió tras el cierre» on the margin screen (*Closing a month*, below). A failed run prints no count.

> **Warning: the first ingestion with no mappings opens many exceptions.** The run always asks Adform for the window, even when no line is mapped yet, and every pair with delivery that matches no mapped line becomes an `unmatched_delivery` exception. On a fresh installation that is one exception per pair with delivery in the whole Adform account, so the "Excepciones" queue fills up at once. Expect it, and work it down by linking each pair to its line (or resolving it) from the queue.

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
tail -n 10 /var/log/adops360/ingestion.log
grep 'exit=' /var/log/adops360/ingestion.log | tail -n 3
```

`exit=0` is a good run. Anything else needs a look: `exit=1` read the `error:` line, `exit=2` find out what held the lock (a manual run left open, or a previous run still going), `exit=3` the configuration of `.env` is incomplete. A day without an `exit=` line means the job did not run (cron stopped, instance down). Re-running a day is safe: the window is idempotent, so `run_ingestion` can be repeated by hand (`--date YYYY-MM-DD` repeats a given day's window).

### Loading a history range

The nightly run only covers the last seven days (D-7 to D-1). It is needed when a **mapped line began more than seven days ago**: the delivery before the window is not loaded by itself. The "Excepciones" and "Catálogo Adform" pages warn about it when a link or a mapping is made for such a line («Esta línea empezó antes de la ventana de siete días…»), and the browser offers no way to load it. Load it by hand, with a range:

```
docker compose -f docker-compose.prod.yml run --rm backend python -m scripts.run_ingestion --from YYYY-MM-DD --to YYYY-MM-DD
```

Rules of the range:

- `--from` and `--to` go together, and not together with `--date`.
- The range is at most 31 days, both ends included, and `--from` cannot be after `--to`.
- `--to` cannot be later than D-1 (yesterday, in the zone of `APP_TIMEZONE`).
- The whole range is asked from Adform in a single request.
- The absence check is not run for a range: the output says `absences: skipped, custom range`.
- The output is counts only, as in the nightly run, and an invalid range prints `status: not configured` and exits with 3.

For a longer history, run it once per block of at most 31 days.

### Equativ: Deal lines, at 06:15 UTC

`Deal` lines are bought through Equativ and ingested with `--dsp Equativ`, through Equativ's asynchronous report. Run it once by hand first, as for Adform:

```
docker compose -f docker-compose.prod.yml run --rm backend python -m scripts.run_ingestion --dsp Equativ
```

Schedule it at **06:15 UTC**, which is 07:15 in Madrid in winter and 08:15 in summer. Equativ bills by UTC day and its days are asked as `Etc/UTC` days, so the time is set in UTC, not in Madrid. A run started before 06:00 UTC still ingests, but skips the check for lines without delivery (`absences: skipped, before 06:00 UTC`), because the previous UTC day may not be complete yet. In the same crontab, after the Adform line:

```
CRON_TZ=UTC
15 6 * * * cd /opt/adops360 && /usr/bin/docker compose -f docker-compose.prod.yml run --rm -T backend python -m scripts.run_ingestion --dsp Equativ >> /var/log/adops360/ingestion-equativ.log 2>&1; echo "$(date -Is) exit=$?" >> /var/log/adops360/ingestion-equativ.log
```

`CRON_TZ` applies to the lines after it, so keep the Adform line, under `CRON_TZ=Europe/Madrid`, before this one. The exit codes are those of Adform.

- **The first history.** The nightly run covers D-7 to D-1. To load the Deal lines that were already running, run it once with a range from the first day of the oldest running Deal line to D-1, with the rules of the range above (at most 31 days per run):

  ```
  docker compose -f docker-compose.prod.yml run --rm backend python -m scripts.run_ingestion --dsp Equativ --from YYYY-MM-DD --to YYYY-MM-DD
  ```

- **Each run leaves one report in the Equativ account.** It is named `adops360-<window>` so it can be recognised, and it is not deleted; deleting them, if Equativ asks, is a change of its own.
- **The company currency is assumed to be EUR.** The amounts are read in the account's company currency and carry no currency column, as Adform's cost does. An account in another currency would need the euro metrics of Equativ instead.
- **Mapping a Deal line.** On the «Catálogo Adform» page, «Vincular una línea de Equativ» lists the lines on Equativ without a mapping; operations writes the line's auction package id (a whole number above zero with no leading zero), suggested from the Equativ packages already seen in the catalogue but never required from it. The mapping counts as validated by the user: Equativ is not asked. **A wrong id is not detected when it is written**: no delivery ever arrives for it, and once its flight has ended it shows up in «Excepciones» as a line without delivery.

### Closing a month

A month can be closed as soon as its last day is loaded: there is no waiting rule. Closing freezes, for every flight that ended in the month, its rates and a snapshot of every figure it shows (revenue, media cost, rebate, platform cost, margin, gross, flags and volumes) together with the delivery they were computed on. All of it goes under one closing header that names the month, the moment, the user, the last day counted (`as_of`) and the latest succeeded ingestion batch of each DSP. **A closed month never moves**: its flights are read only from their snapshots.

- **The ingestion and the unlinking still rewrite the delivery of a closed month.** The nightly runs replace D-7 to D-1 and a range run replaces its range whatever the closing, and unlinking a line removes its delivery. The stored delivery keeps being the DSP's latest truth, but no figure of a closed flight, line, campaign or total changes. A run prints how many of its days fell in a closed month (`closed_month_days`).
- **The margin screen flags a closed flight whose delivery changed.** When the delivery stored now would move its margin by 1.00 € or more, or its delivered volume by 1 % or more, the flight is tagged «Cambió tras el cierre», with the margin it would have with today's delivery and the differences. That margin uses the closing's rebate and rates, only the delivery changes, and no total adds it. Lines, campaigns and the period count the tagged flights. A closed month is not reopened: if the new delivery is right, the difference is settled outside the application.
- **A month may be closed more than once.** A flight registered in a month already closed stays pending close, and blocks closing the later months of its year (`previous_month_open`), until the month is closed again. That closing freezes it under a second header, the closing response says how many headers the month holds (`closings`), and the figures of the earlier closing do not change.
- **A month with a target flight waits for its DSP.** It cannot be closed until that DSP has a succeeded run whose window includes the month's last day: the closing answers `month_delivery_not_loaded` until then.

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

The status endpoint is the end-to-end check: it needs a valid Entra access token, the user's roles in the database and the migrated schema.

Without a token it must answer 401:

```
curl -s -o /dev/null -w '%{http_code}\n' https://<SERVER_NAME>/api/campaign-status
```

With a token, sign in to the application with the first user (section 11), open the browser's developer tools, and copy the `Authorization: Bearer ...` value of any request to `/api/`. Read it into a shell variable without echoing it or leaving it in the history, and use it once:

```
read -rs ACCESS_TOKEN
curl -fsS -H "Authorization: Bearer $ACCESS_TOKEN" https://<SERVER_NAME>/api/campaign-status
unset ACCESS_TOKEN
```

On a fresh database the answer is `200` with `[]` (no campaign is running yet). Every role of the access matrix (`operations`, `business`, `finance` and `trading`) may read the status. Otherwise:

- `401` (`unauthenticated`): the token is not accepted. Check `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID` in `.env` against the production registration, and that the token is the access token, version 2, with the scope `access_as_user`: no other token of the sign-in is accepted.
- `403 user_not_registered`: no user matches the token's link or its email, or the token carries no email and the user is not linked yet (section 5, the optional claim, and section 11).
- `403 identity_link_conflict`: the email matches a user linked to another identity.
- `403 user_inactive`: the user has been deactivated.
- `403 missing_role`: the user exists but holds none of the roles the route accepts.

The same in the browser: the "Estado" page shows "No hay campañas en curso" rather than an error.

### The ingestion

Run the command once by hand (section 12) and check that its output starts with `status: succeeded` and that the exit code is 0:

```
docker compose -f docker-compose.prod.yml run --rm backend python -m scripts.run_ingestion; echo "exit=$?"
```

With the Equativ credentials set, do the same with `--dsp Equativ`. Once campaigns and their DSP mappings exist, the "Excepciones" page lists what a run could not place.

## 15. Logs and restarts

Every service rotates its logs (`json-file`, 10 MB by 5 files) and restarts unless stopped by hand, including after a reboot of the instance.
