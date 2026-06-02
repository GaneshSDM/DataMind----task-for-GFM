# Integrating the Docker setup into the DataMind git repo

This zip mirrors the repo layout. Unzipping it into the repo root drops every file into the
right place. Only one existing file is overwritten: `backend/app/agents/http_clients.py`
(patched to read agent URLs from env vars, with localhost fallbacks — your `start_all.py`
workflow keeps working unchanged).

## Contents

```
docker-compose.yml
.dockerignore
INTEGRATE.md                     ← this file
DOCKER_DEPLOY.md                 ← full deployment + troubleshooting guide
docker/
├── Dockerfile.backend
├── Dockerfile.agents
├── Dockerfile.frontend
├── nginx.conf
├── requirements.agents.txt
├── entrypoint-backend.sh
├── entrypoint-aria.sh
└── entrypoint-sage.sh
backend/app/agents/http_clients.py   ← REPLACES the existing file
```

## Steps

```bash
# 1. From the repo root, on a new branch
cd /path/to/DataMind
git checkout -b feat/docker-compose

# 2. Unzip this archive into the repo root (it merges into existing folders)
unzip datamind-docker.zip -d .
#   On Windows PowerShell:
#   Expand-Archive datamind-docker.zip -DestinationPath .

# 3. Confirm the patched file landed and review the diff
git status
git diff backend/app/agents/http_clients.py

# 4. Make the entrypoint scripts executable and preserve that bit in git
chmod +x docker/*.sh
git update-index --chmod=+x docker/entrypoint-backend.sh
git update-index --chmod=+x docker/entrypoint-aria.sh
git update-index --chmod=+x docker/entrypoint-sage.sh

# 5. Stage and commit
git add docker-compose.yml .dockerignore docker/ backend/app/agents/http_clients.py \
        INTEGRATE.md DOCKER_DEPLOY.md
git commit -m "Add Docker Compose stack (nginx + backend + 6 agents)"

# 6. Push
git push -u origin feat/docker-compose
```

## After merging — run it on EC2

```bash
git pull
# set SEED_DB=true in backend/.env for the very first boot only
docker compose up -d --build
docker compose ps        # wait for all services to be healthy
```

Open `http://<ec2-public-dns>/` and log in with `admin@slm.local / Admin@1234`.
Then trim the EC2 Security Group to ports 80, 443, and 22 (your IP); remove 5173 and 8000.

See `DOCKER_DEPLOY.md` for the full explanation, startup ordering, schema refresh, HTTPS, and troubleshooting.

## Notes

- `.gitignore` in the repo already ignores `schema_reference.json`, `pipeline_queue/*.json`,
  `logs/`, and `node_modules` — the `.dockerignore` here keeps those out of the build context too.
- If a CRLF/line-ending issue makes the `.sh` scripts fail in the container, run
  `sed -i 's/\r$//' docker/*.sh` before building.
