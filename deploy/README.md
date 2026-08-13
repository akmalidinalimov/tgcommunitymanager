# Deploying

Docker Compose pushed through the **Hostinger API**. There is no SSH key for this
VPS, and this is how `freelanceai` already ships — one deployment pattern on the
box, not two.

**Target:** VM `1411263` (`srv1411263.hstgr.cloud`), as a project named
`tgcommunitymanager` **alongside** `freelanceai` and `smmuzbot`.

> **Never touch `smmuzbot` or `freelanceai`.** The Hostinger docker endpoint
> replaces the project you name it, so always name `tgcommunitymanager`
> explicitly. `smmuzbot` is the founders' live SMM bot.

---

## One-time setup

### 1. Push to GitHub

The image is built by GitHub Actions, not locally — Docker is not installed on
the founders' laptop, and a build that depends on whose machine it ran from is a
build that breaks at the worst moment.

```bash
git checkout main
git merge docs/design-spec
git push origin main
```

Watch it at `https://github.com/akmalidinalimov/tgcommunitymanager/actions`.
The workflow runs the test suite first — a broken bot posts to 3,326 people, so
tests gate the push rather than following it.

Result: `ghcr.io/akmalidinalimov/tgcommunitymanager:latest`

### 2. Make the package readable by the VPS

GHCR packages default to private. Either:

- **Make it public** — GitHub → Packages → `tgcommunitymanager` → Package
  settings → Change visibility → Public. Simplest, and the image contains no
  secrets: every credential arrives as an environment variable at run time.
- **Or keep it private** and run `docker login ghcr.io` on the VPS with a PAT
  that has `read:packages`.

### 3. Deploy

Environment variables are passed separately from the compose file and never
committed. Values come from `.env`.

Via the Hostinger MCP or API:

```
project_name: tgcommunitymanager
virtualMachineId: 1411263
content:     <contents of deploy/docker-compose.yml>
environment: TELEGRAM_BOT_TOKEN=...
             TELEGRAM_BOT_USERNAME=malikamanager_bot
             TELEGRAM_CHANNEL_ID=-1002708742288
             TELEGRAM_DISCUSSION_GROUP_ID=-1004430366406
             TELEGRAM_CHANNEL_USERNAME=aicreatorsuz
             TELEGRAM_ADMIN_CHAT_ID=6542876935
             TELEGRAM_APPROVER_IDS=6542876935
             ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Verify

Check the container is `running` and healthy. The healthcheck runs
`python -m app --preflight`, so a bot that has lost admin rights or had privacy
mode re-enabled reports **unhealthy** rather than sitting there hearing nothing.

Then confirm in Telegram: the next slot should produce an approval card in the
admin chat, and a comment on any post should draw a reply or a reaction.

---

## Known Hostinger behaviour

Both documented in `freelanceai/deploy/deploy-vps.ps1` from experience:

- **The compose `content` field is capped at 8192 characters.** Ours is ~850, so
  there is plenty of headroom — but keep configuration in environment variables
  rather than inline YAML.
- **Created-not-started flake.** Compose-up sometimes recreates containers
  without starting them. If the project shows `created` rather than `running`,
  call project start explicitly. It is not a failure, just a retry.

## Updating

Push to `main`. Actions rebuilds `:latest`, then redeploy the same project to
pull it. State lives in the `tgcm-data` volume and survives redeploys — the
SQLite database, and with it every thread mapping. **Do not delete that volume**:
the channel-post to comment-thread mapping cannot be rebuilt, because Telegram
announces it once and drops updates older than 24 hours.

## Rollback

Deploy again with the image tag pinned to a previous commit SHA instead of
`latest`. Every build is tagged with its SHA for exactly this.

## Backups

The whole state of the bot is `/app/data` inside the `tgcm-data` volume — the
SQLite file and generated media. Copying it is the backup. Worth a weekly copy
off the box, since a VM loss otherwise takes every thread mapping with it.
