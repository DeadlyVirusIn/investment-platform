# Stage-B Pre-Approval Readiness — 48h Observation + Disk Expansion

Status at 2026-07-15 23:2x UTC: **Workstream 2 (disk) COMPLETE · Workstream 1
(48h observation) IN PROGRESS — earliest valid completion 2026-07-17 22:36
UTC.** No migration applied; no flag enabled; no code deployed; DB at
`109_research_run`.

## Workstream 2 — disk expansion: **COMPLETE (target exceeded)**

Finding: the OCI boot volume was **already 50GB at the cloud layer**
(`Disk /dev/sda: 50.0GB`, GPT, sda3 = 44.5GiB LVM PV, growpart NOCHANGE)
— the historical 30→50GB expansion had been done cloud-side but never
propagated into the guest: VG `ocivolume` was fully allocated as root
29.5GiB + `oled` 15GiB (XFS, **3% used** — PCP/crash data only). No
cloud operation was needed or performed; no reboot; PostgreSQL
`StartedAt` unchanged.

Guest reallocation executed (fstab uses the device-mapper path, so a
same-name LV recreation needs no fstab edit; SELinux contexts restored):

1. `systemctl stop pmlogger pmie pmcd` (the only writers, verified via
   lsof/fuser)
2. backup `/var/oled` → `~/backups/oled_backup_20260715.tar.gz` (109MB)
3. `umount /var/oled` → `lvremove ocivolume/oled` →
   `lvcreate -L 4G -n oled` → `mkfs.xfs` → `mount /var/oled` → restore
   + `restorecon -R`
4. `lvextend -l +100%FREE ocivolume/root` → `xfs_growfs /` (online)
5. PCP restarted

| Metric | Before | After |
|---|---|---|
| root LV / filesystem | 29.5GiB / 30G @ **92%** (2.6G free) | **40.5GiB / 41G @ 67% (14G free)** |
| /var/oled | 15GiB @ 3% | 4GiB @ 6% (contents preserved) |
| Services | 6/6 healthy | 6/6 healthy; api 200; zero restarts |

Target (≥8–10GB free, <75%) exceeded. Headroom now covers: fresh prod
backup (~0.45GB), WAL, migration growth (~1MB!), one rollback image
generation, logs.

### Backup / rollback-image inventory (retention policy)

| Item | Class |
|---|---|
| `compose-*:pre-elite-rebuild-20260715` (3 tags) | REQUIRED current rollback |
| `~/backups/proddb_pre_p1_20260715.dump` (453,912,898B, sha256 `7586097d…`) | REQUIRED fresh P-1 backup (pre-cleanup state) |
| `~/backups/checkout_drift_20260715.tar.gz` (124KB) | web/source rollback + P-2 evidence — retain |
| `~/backups/oled_backup_20260715.tar.gz` (109MB) | oled restore point — retain ≥30d |
| local `.backups/proddb_v1_20260714.dump` (sha256 `6e3d8be8…`) | known-good historical backup (off-VM copy!) — retain |
| local `.backups/p1_orphan_archive_prod_20260715.csv` | P-1 audit manifest — retain |
| stageb1 image tags | superseded — already retired 2026-07-15 (IDs recorded) |

Nothing was pruned in this workstream.

## Workstream 1 — 48h observation: **IN PROGRESS**

Window: **2026-07-15 22:36 UTC → 2026-07-17 22:36 UTC.**

### Baseline (captured 2026-07-15 23:15 UTC)

SHA `7e0af44` · images api `ae721095…` / cron `c7da1bbd…` / tickloop
`c6c84a13…` · StartedAt 22:12/22:13/22:13/22:36 (db 2026-06-23,
untouched) · restarts **0** on all containers · DB `109_research_run` ·
orphans **0** · FK `convalidated = t` · `research_run` **0** · paper
books 54 user / 19 engine-side · no Elite env vars · next scheduled:
`run_paper_trading` 2026-07-15 23:30 UTC, `refresh_company_names` 05:30,
plus the 03:30 ET supercronic daily loop.

### Nightly cycles to observe (checklist per cycle)

- [ ] Cycle 1: night of 2026-07-15→16 (23:30 UTC run_paper_trading +
      07:30 UTC daily loop)
- [ ] Cycle 2: night of 2026-07-16→17

Per cycle record: scheduler claim/job identity/status/duration; engine
book count vs user-book exclusion (**invariant: engine-selected ∩
`user:%` = ∅**); recommendations generated; outcomes scored; positions
opened/closed; error summaries; retries; restarts; DB errors; API/WebUI
health after. Continuous: restart counts, 5xx, missing-relation errors,
orphan recurrence (must stay 0), `research_run` writes (must stay 0),
Elite route spot-checks (must stay 404), disk growth.

### Verification queries (run at each check)

```sql
SELECT count(*) FROM job_run jr LEFT JOIN job_schedule js
  ON js.id = jr.job_schedule_id WHERE js.id IS NULL;   -- 0
SELECT count(*) FROM research_run;                      -- 0
SELECT js.name, jr.status, jr.started_at, jr.duration_seconds
  FROM job_run jr JOIN job_schedule js ON js.id = jr.job_schedule_id
  WHERE jr.started_at > now() - interval '1 day'
  ORDER BY jr.started_at DESC LIMIT 12;
SELECT count(*) FROM paper_trade pt JOIN paper_portfolio pp
  ON pp.id = pt.portfolio_id WHERE pp.name LIKE 'user:%'
  AND pt.created_at > '2026-07-15 22:36+00';            -- 0 (isolation)
```

### Verdict placeholder

To be completed after 2026-07-17 22:36 UTC with both cycles recorded.
Current continuous-check state (first hour): all green.

## Overall verdict (as of 2026-07-15): **BLOCKED — time-gated only**

Blocking item: the 48h window simply has not elapsed. Disk is done. All
other READY conditions currently hold (DB 109, flags off, orphans 0,
services healthy, 14GB free). Re-run the observation checks after
**2026-07-17 22:36 UTC**; if both nightly cycles are green, the verdict
flips to READY FOR APPROVAL POINT B.
