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

## 10. The first user

The development seed is not in the production image. Create the first user, with the roles you need, with:

```
docker compose -f docker-compose.prod.yml run --rm backend \
  python -m scripts.grant_roles <email> operations [business] [finance]
```

Use the email Cognito puts in the token, spelled exactly the same: it is the only link between Cognito and the local user. The command creates the user if it does not exist, creates the requested role rows if they are missing, and prints counts only. Running it again changes nothing.

**Pending, outside this change:** the master data (agencies, advertisers, DSPs, channels, formats...) is empty in a fresh production database and nothing here loads it; the "new campaign" form needs it.

## 11. Nightly ingestion

The ingestion is a command for the host scheduler, not a container. It needs the Adform credentials in `.env`:

```
docker compose -f docker-compose.prod.yml run --rm backend python -m scripts.run_ingestion
```

Run it once by hand and reconcile the figures before scheduling it (for example from the host's crontab, shortly after midnight, Europe/Madrid time). Exit codes: 0 succeeded, 1 failed, 2 another run holds the lock, 3 configuration is missing.

## 12. Checking a deployment

- `curl -fsS https://<SERVER_NAME>/api/health` answers 200.
- `curl -sI http://<SERVER_NAME>/` answers 301 to HTTPS.
- `docker compose -f docker-compose.prod.yml ps` shows every service as healthy.
- From outside, `nmap` of the instance shows only 22, 80 and 443.

## 13. Logs and restarts

Every service rotates its logs (`json-file`, 10 MB by 5 files) and restarts unless stopped by hand, including after a reboot of the instance.
