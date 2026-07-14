# Production Disk Remediation Plan (PREPARED — read-only evidence, nothing deleted)

VM `ptcgp-server` (150.136.38.189). Read-only inventory 2026-07-11. **No
deletion performed; no cleanup executed.** Both plans are approval-gated.

## Inventory (root `/dev/mapper/ocivolume-root`, 30 GB, 25 GB used, 4.7 GB free, 85%)

| Consumer | Size | Reclaimable | Protected? |
|---|---|---|---|
| `/var/lib/docker` total | 7.2 GB | — | mixed |
| Docker images (8) | 4.09 GB | 1.508 GB per `system df` | see below |
| Docker local volumes (6, active) | 4.23 GB | 0 B | **YES** (DB data) |
| Docker containers (6, running) | 111 MB | 0 B | YES |
| Build cache | 0 B | 0 B | — |
| `investment-platform/.backups` | 1.3 GB | ~440 MB (1 redundant dump) | partial |
| `arthos-backups` (p1-20260708) | 407 MB | 0 (single) | keep |
| `arthos-deploy-p1` | 345 MB | maybe | deploy artifact |
| `arthos-migrate-109` | 181 MB | maybe | one-shot migration dir |
| `arthos-deploy-b1` | 179 MB | 0 | **YES** (running release source) |
| systemd journal | 91 MB | ~40 MB | vacuumable |
| core dumps | 0 | 0 | — |
| stopped containers | 0 | 0 | — |

**Docker images breakdown:** `compose-{api,worker-cron,worker-tickloop}:latest`
(3×1.05 GB, running) + `compose-{...}:rollback-stageb1` (3×1.05 GB) + postgres:17
(414 MB) + node:20 (192 MB) + caddy (84 MB) + alpine (13 MB). The 1.508 GB
"reclaimable" is almost entirely the **rollback-stageb1 images — PROTECTED**
(they are the Stage-B2 rollback requirement). They must NOT be pruned.

**Backups (`.backups`, 1.3 GB):** `proddb_full_20260711_090002` (443 MB),
`proddb_full_20260710_120852` (438 MB), `proddb_full_20260710_090002` (438 MB),
`prod_pre_seed_…` (203 KB). The two 07-10 dumps are same-day duplicates.

## Plan 1 — safe targeted cleanup (recover enough to drop below 85% NOW)

Ordered by safety; each item independently approvable. **Protected artifacts
never touched:** running images, `rollback-stageb1` images, active DB volumes,
`arthos-deploy-b1`, the newest daily prod backup + pre-seed.

1. **Delete the redundant same-day prod backup** (~440 MB): keep
   `proddb_full_20260710_120852` (newest 07-10) + `proddb_full_20260711_090002`
   (newest 07-11) + pre-seed; remove `proddb_full_20260710_090002`. Verify the
   two kept dumps pass `gzip -t` before removing the third. → ~440 MB.
2. **Vacuum the journal** to a bounded size (`journalctl --vacuum-size=50M`).
   → ~40 MB.
3. **(optional, verify-first) archive `arthos-migrate-109`** (181 MB) off-VM if
   the 109 migration is confirmed applied in prod (it is) and the dir is a
   one-shot artifact — tar+scp off-box, then remove. → ~181 MB.
4. **(optional) `docker image prune`** (dangling only, NOT `-a`) — currently
   ~0 B dangling; run only to sweep future untagged layers. Never `prune -a`
   (would remove rollback-stageb1).

**Net immediate reclaim (items 1–2): ~480 MB** → used 25 GB → ~24.5 GB → **~82%**
(below the 85% gate). Item 3 adds headroom to ~81%.

Retention policy to encode (prevents recurrence): keep **1 prod DB dump per
calendar day, last 7 days**, plus the pre-seed; a nightly prune enforces it.
The current backup script writes 2–3/day with no prune — that is the growth
source.

**Every cleanup command requires separate owner approval + a fresh vm-guard
marker. None are executed here.**

## Plan 2 — permanent fix: OCI boot-volume expansion 30 GB → ≥50 GB

The cleanup buys headroom but the boot volume is structurally undersized for
Docker (7.2 GB) + backups + two co-tenant projects (ptcgpb-bot 903 MB). Expand:

1. **OCI console / CLI:** grow the boot volume `ocivolume` from 30 GB to 50 GB
   (online resize supported; no instance stop required on recent shapes —
   confirm shape first).
2. **Rescan + grow the block device** on the VM:
   `sudo dd iflag=direct if=/dev/oracleoci/oraclevda of=/dev/null count=1` (rescan),
   then `sudo /usr/libexec/oci-growfs -y` (OCI's growfs handles the partition +
   LVM PV + `ocivolume-root` LV + XFS grow in one step on OL). Verify with
   `df -h /` → ~45 GB free ceiling, ~55% used.
3. **Backup first:** the newest prod dump is off-critical-path but take a fresh
   `make db-backup` + confirm an off-VM copy before any volume op.

**Rollback:** OCI boot-volume grow is one-way (cannot shrink), but non-
destructive — if growfs fails mid-step the filesystem is untouched until the
final XFS grow; re-run growfs. No data risk when a current off-VM backup exists.
**Hard stop:** volume expansion is a production infra change — owner approval +
vm-guard marker required; not executed here.

## Recommendation
Do **Plan 1 items 1–2** first (gets below 85%, unblocks the Stage-B1 disk gate),
then schedule **Plan 2** as the permanent fix and encode the 7-day backup
retention prune. Sequence both behind explicit owner approval.
