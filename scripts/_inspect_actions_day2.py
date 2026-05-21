"""One-shot inspection script: dismissed/acted preservation on rerun."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import ActionItem
from apps.api.src.domain.actions import repo
from apps.api.src.domain.actions.materializer import materialize_actions_for_day

AS_OF = dt.date(2026, 3, 13)


def main() -> None:
    with SessionLocal() as s:
        before = list(s.scalars(select(ActionItem).where(ActionItem.as_of_date == AS_OF)))
        before_map = {a.id: a.status for a in before}
        pending_before = [a for a in before if a.status == "pending"]
        print(f"T0: total={len(before)} pending={len(pending_before)} "
              f"dismissed={sum(1 for a in before if a.status=='dismissed')} "
              f"acted={sum(1 for a in before if a.status=='acted')}")

        if len(pending_before) < 3:
            print("not enough pending rows to run test — resetting by deleting all rows")
            for a in before:
                s.delete(a)
            s.commit()
            materialize_actions_for_day(s, AS_OF)
            before = list(s.scalars(select(ActionItem).where(ActionItem.as_of_date == AS_OF)))
            pending_before = [a for a in before if a.status == "pending"]

        dismissed_ids = [pending_before[0].id, pending_before[1].id]
        for aid in dismissed_ids:
            repo.dismiss(s, aid, reason="inspection_test")
        s.commit()

        acted_id = pending_before[2].id
        acted_row = s.get(ActionItem, acted_id)
        acted_row.status = "acted"
        acted_row.acted_at = dt.datetime.now(dt.timezone.utc)
        s.commit()

        mid = list(s.scalars(select(ActionItem).where(ActionItem.as_of_date == AS_OF)))
        print(f"T1 (after dismiss+act): "
              f"pending={sum(1 for a in mid if a.status=='pending')} "
              f"dismissed={sum(1 for a in mid if a.status=='dismissed')} "
              f"acted={sum(1 for a in mid if a.status=='acted')}")

        n = materialize_actions_for_day(s, AS_OF)
        print(f"T2 rematerialize wrote={n}")

        after = list(s.scalars(select(ActionItem).where(ActionItem.as_of_date == AS_OF)))
        after_map = {a.id: a.status for a in after}

        # CHECK 1 — IDs preserved (no new UUIDs for existing (as_of,asset,kind,origin))
        ids_preserved = set(before_map.keys()) == set(after_map.keys())
        print(f"CHECK ids_preserved: {ids_preserved}")

        # CHECK 2 — dismissed rows stay dismissed
        for aid in dismissed_ids:
            post = s.get(ActionItem, aid)
            assert post.status == "dismissed", f"RESURRECTION BUG {aid} status={post.status}"
            assert post.dismiss_reason == "inspection_test", f"dismiss_reason lost"
        print(f"CHECK dismissed_stays_dismissed: True (count=2)")

        # CHECK 3 — acted row stays acted
        acted_post = s.get(ActionItem, acted_id)
        assert acted_post.status == "acted", f"ACTED LOST status={acted_post.status}"
        print(f"CHECK acted_stays_acted: True")

        # CHECK 4 — pending count decreased by exactly 3
        pending_after = [a for a in after if a.status == "pending"]
        expected = len(pending_before) - 3
        print(f"CHECK pending_count: before={len(pending_before)} after={len(pending_after)} expected={expected}")
        assert len(pending_after) == expected

        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
