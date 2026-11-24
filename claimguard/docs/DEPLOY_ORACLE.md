# Deploy ClaimGuard on Oracle Cloud (Always Free)

OCI **Cloud Shell** is a browser terminal for managing your tenancy. It cannot serve a public website (no inbound ports, and the session times out). Use it to create and reach a **Compute VM**, which runs the stack.

## 1. Create the VM

1. Console → Compute → Instances → Create instance.
2. Image: **Canonical Ubuntu 24.04**. Shape: **VM.Standard.A1.Flex** (Ampere, Always Free), 2 OCPU / 12 GB is plenty. All images are multi-arch, so ARM works.
3. Add your SSH public key (or generate one in Cloud Shell: `ssh-keygen -t ed25519` and paste `~/.ssh/id_ed25519.pub`).
4. Note the public IP.

## 2. Open the ports

Two firewalls both need to allow traffic.

**VCN Security List** (Networking → Virtual cloud networks → your VCN → Security Lists → Default → Add ingress rules): source `0.0.0.0/0`, TCP, destination ports `80`, `443` (and `8080` if you serve n8n without a domain).

**Ubuntu iptables** (Oracle images block everything except 22 by default):

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8080 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Install Docker

```bash
ssh ubuntu@YOUR_IP
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
docker compose version
```

## 4. Get the code and configure

```bash
git clone https://github.com/YOU/claimguard.git ~/claimguard   # or scp the folder
cd ~/claimguard
cp .env.example .env
nano .env
```

- **IP only:** keep `APP_DOMAIN=:80`, `N8N_DOMAIN=:8080` and set `N8N_PUBLIC_URL=http://YOUR_IP:8080/`.
- **With a domain (recommended, free HTTPS):** create DNS A records `claimguard.example.com` and `n8n.claimguard.example.com` pointing at the IP, then set `APP_DOMAIN`, `N8N_DOMAIN`, `N8N_PUBLIC_URL=https://n8n.claimguard.example.com/`, `N8N_PROTOCOL=https` and `N8N_SECURE_COOKIE=true`. Caddy fetches the Let's Encrypt certificates by itself.
- **Agent LLM (optional):** set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` for any OpenAI-compatible API. Without them the agent runs its deterministic offline planner.

## 5. Start

```bash
docker compose up -d --build          # the build runs data contracts, training and the quality gate
docker compose ps
curl -s http://127.0.0.1:8000/api/health
```

Open `http://YOUR_IP` (or your domain).

Local LLM instead of an API (needs about 4 GB RAM for a 3B model):

```bash
docker compose --profile llm up -d
docker compose exec ollama ollama pull qwen2.5:3b
# .env: LLM_BASE_URL=http://ollama:11434/v1  LLM_MODEL=qwen2.5:3b  LLM_API_KEY=ollama
docker compose up -d app
```

## 6. Load the n8n workflows

```bash
docker compose exec n8n n8n import:workflow --separate --input=/workflows
for id in $(docker compose exec -T n8n n8n list:workflow | cut -d'|' -f1); do
  docker compose exec -T n8n n8n publish:workflow --id=$id
done
docker compose restart n8n
```

Open n8n (`http://YOUR_IP:8080` or your n8n domain) and create the owner account. Then test:

```bash
curl -X POST http://127.0.0.1:5678/webhook/claim-intake -H 'content-type: application/json' \
  -d '{"claim_id":"TEST-1","days_after_policy_start":5,"description_matches_damage":"no","document_manipulated":"yes"}'
# {"claim_id":"TEST-1","band":"red","score":55,...}
```

Set `ALERT_WEBHOOK_URL` (a Slack, Teams or Discord incoming webhook) in `.env` to get alerts.

## 7. Continuous deployment from GitHub

Add these repository secrets (Settings → Secrets and variables → Actions):

| secret | value |
|---|---|
| `ORACLE_HOST` | VM public IP |
| `ORACLE_USER` | `ubuntu` |
| `ORACLE_SSH_KEY` | private key that can log in to the VM |
| `ORACLE_APP_DIR` | `~/claimguard` (optional) |

Every push to `main` then runs lint → data contracts → train + gate → tests → Docker build + smoke test → SSH deploy (`git pull && docker compose up -d --build`). For the weekly n8n drift workflow to trigger a retrain, put `GITHUB_REPO=owner/repo` and a fine-grained `GITHUB_TOKEN` (Actions: read and write) in the server's `.env`.

## Operations

```bash
docker compose logs -f app            # API logs
docker compose exec app python -m ml.drift   # drift check by hand
docker compose pull && docker compose up -d --build   # update
```
