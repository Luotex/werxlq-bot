from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

VERSION = 2
FINAL_STATUSES = ("accepted", "rejected", "cancelled")

def _defaults() -> dict:
    return {
        "version": VERSION,
        "offset": 0,
        "admins": [],
        "sessions": {},
        "orders": {},
        "closed": {},
        "totals": {
            "closed": 0,
            "accepted": 0,
            "rejected": 0,
            "cancelled": 0,
        },
        "msgmap": {},
        "counter": 1,
    }

def _proof_summary(proof: dict) -> dict:
    if not isinstance(proof, dict):
        return {}
    if proof.get("kind") not in ("photo", "document", "video", "text"):
        return {}
    kept: dict = {"kind": proof["kind"]}
    if proof.get("file_id"):
        kept["file_id"] = proof["file_id"]
    if proof.get("name"):
        kept["name"] = proof["name"]
    if proof.get("text"):
        kept["text"] = str(proof["text"])[:300]
    if proof.get("caption"):
        kept["caption"] = str(proof["caption"])[:300]
    return kept

def summary(order: dict) -> dict:
    raw = order.get("proofs") or [order.get("proof")]
    kept_proofs = [item for item in (_proof_summary(proof) for proof in raw[:5]) if item]

    return {
        "id": order.get("id"),
        "status": order.get("status"),
        "nick": order.get("nick"),
        "name": order.get("name") or "",
        "username": order.get("username") or "",
        "user_id": order.get("user_id"),
        "chat_id": order.get("chat_id"),
        "created_at": order.get("created_at"),
        "updated_at": order.get("updated_at") or order.get("created_at"),
        "proof": kept_proofs[0] if kept_proofs else {},
        "proofs": kept_proofs,
        "proofs_count": len(kept_proofs),
    }

class Store:
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self.data = _defaults()
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            backup = self.path.with_suffix(self.path.suffix + ".corrupt")
            log.error("Не удалось прочитать %s (%s), сохраняю копию в %s", self.path, exc, backup)
            try:
                shutil.copyfile(self.path, backup)
            except OSError:
                pass
            return

        if not isinstance(loaded, dict):
            log.error("Файл %s повреждён: ожидался объект", self.path)
            return

        for key, value in loaded.items():
            if key in self.data:
                self.data[key] = value

        if int(loaded.get("version") or 1) < VERSION:
            self._migrate()

    def save(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except OSError as exc:
            log.error("Не удалось сохранить состояние в %s: %s", self.path, exc)

    def _migrate(self) -> None:
        totals = self.data.setdefault("totals", _defaults()["totals"])
        closed = self.data.setdefault("closed", {})
        moved = 0
        for order_id, order in list(self.orders.items()):
            if not isinstance(order, dict):
                continue
            status = order.get("status")
            if status not in FINAL_STATUSES:
                continue
            closed.setdefault(str(order_id), summary(order))
            totals[status] = int(totals.get(status) or 0) + 1
            totals["closed"] = int(totals.get("closed") or 0) + 1
            self.orders.pop(order_id, None)
            moved += 1

        self.data["version"] = VERSION
        if moved:
            log.info("state.json обновлён до версии %s: %s закрытых заявок в архив", VERSION, moved)
            self.save()

    @property
    def orders(self) -> dict:
        return self.data.setdefault("orders", {})

    @property
    def closed(self) -> dict:
        return self.data.setdefault("closed", {})

    @property
    def totals(self) -> dict:
        return self.data.setdefault("totals", {})

    @property
    def sessions(self) -> dict:
        return self.data.setdefault("sessions", {})

    def next_order_id(self) -> str:
        number = int(self.data.get("counter") or 1000)
        self.data["counter"] = number + 1
        return str(number)

    def archive(self, order: dict, keep: int = 25) -> bool:
        order_id = str(order.get("id"))
        status = order.get("status") or ""
        totals = self.totals
        if status in FINAL_STATUSES:
            totals[status] = int(totals.get(status) or 0) + 1
            totals["closed"] = int(totals.get("closed") or 0) + 1

        kept = bool(keep and keep > 0)
        if kept:
            self.closed[order_id] = summary(order)
        else:
            self.closed.pop(order_id, None)

        self.orders.pop(order_id, None)
        if kept:
            self._trim_closed(keep)

        self._drop_references()
        return kept

    def _trim_closed(self, keep: int) -> None:
        if len(self.closed) <= keep:
            return
        ordered = sorted(
            self.closed.items(),
            key=lambda item: (item[1] or {}).get("updated_at") or (item[1] or {}).get("created_at") or 0,
            reverse=True,
        )
        for order_id, _ in ordered[keep:]:
            self.closed.pop(order_id, None)

    def _drop_references(self) -> None:
        alive = {str(key) for key in self.orders} | {str(key) for key in self.closed}

        msgmap = self.data.get("msgmap") or {}
        for key in [
            key
            for key, value in msgmap.items()
            if isinstance(value, dict)
            and value.get("order_id")
            and str(value.get("order_id")) not in alive
        ]:
            msgmap.pop(key, None)

        for key in [
            key
            for key, value in self.sessions.items()
            if isinstance(value, dict)
            and value.get("order_id")
            and str(value.get("order_id")) not in alive
        ]:
            self.sessions.pop(key, None)

    def clear_sessions_for(self, order_id: str) -> None:
        order_id = str(order_id)
        for key in [
            key
            for key, value in self.sessions.items()
            if isinstance(value, dict) and str(value.get("order_id")) == order_id
        ]:
            self.sessions.pop(key, None)

    def stats(self) -> dict:
        result = {"total": 0, "pending": 0, "awaiting_product": 0,
                  "accepted": 0, "rejected": 0, "cancelled": 0, "closed_archived": len(self.closed)}
        for order in self.orders.values():
            if not isinstance(order, dict):
                continue
            result["total"] += 1
            status = order.get("status", "pending")
            if status in result:
                result[status] += 1

        totals = self.totals
        for status in FINAL_STATUSES:
            result[status] += int(totals.get(status) or 0)
        result["total"] += int(totals.get("closed") or 0)
        return result
