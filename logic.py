from __future__ import annotations

import html
import logging
import re
import time
from dataclasses import dataclass, field

import texts as T
from api import TelegramAPI, TelegramError
from store import Store

log = logging.getLogger(__name__)

CMD_RE = re.compile(r"^/([A-Za-z0-9_]+)(?:@\w+)?(?:\s+(.*))?$", re.S)
CARD_RE = re.compile(r"\d(?:[ \-]?\d){12,18}")

BUYER_PROOF_KINDS = {"photo", "document", "video", "text"}
PRODUCT_KINDS = {"photo", "document"}
ATTACHMENT_KINDS = {"photo", "document", "video"}

MAX_PROOFS = 5
MAX_MSGMAP = 300
MAX_CHAT_HISTORY = 20

@dataclass
class Config:
    admin_username: str = "werxlq"
    admin_usernames: list[str] = field(default_factory=list)
    bot_username: str = ""
    bot_created: str = ""
    bot_developer: str = ""
    bot_for: str = ""
    intro: str = "Это бот для сигн от Вельвет."
    admin_ids: list[int] = field(default_factory=list)
    bank: str = "Сбер"
    card_number: str = "2202 2084 5871 1745"
    card_holder: str = "Арина Е."
    price: str = ""
    product: str = "сигну"
    support_contact: str = ""
    rate_limit_count: int = 20
    rate_limit_window: int = 60
    keep_closed: int = 25

    @property
    def all_admin_usernames(self) -> list[str]:
        result: list[str] = []
        for name in [self.admin_username, *self.admin_usernames]:
            clean = (name or "").strip().lstrip("@").lower()
            if clean and clean not in result:
                result.append(clean)
        return result

def luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0

def looks_like_card(text: str, seller_digits: str = "") -> bool:
    for match in CARD_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(0))
        if not 13 <= len(digits) <= 19:
            continue
        if seller_digits and digits == seller_digits:
            continue
        if luhn(digits):
            return True
    return False

class BotLogic:
    def __init__(self, api, store: Store, cfg: Config, strict: bool = False) -> None:
        self.api = api
        self.store = store
        self.cfg = cfg
        self.strict = strict
        self._hits: dict[int, list[float]] = {}
        self._seller_digits = re.sub(r"\D", "", cfg.card_number or "")

    @property
    def data(self) -> dict:
        return self.store.data

    def _now(self) -> float:
        return time.time()

    def _fmt_time(self, timestamp: float) -> str:
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))

    def _save(self) -> None:
        self.store.save()

    def _send(self, chat_id: int, text: str, keyboard=None):
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if keyboard:
            params["reply_markup"] = {"inline_keyboard": keyboard}
        return self.api.call("sendMessage", **params)

    def _try_send(self, chat_id: int, text: str, keyboard=None):
        try:
            return self._send(chat_id, text, keyboard)
        except TelegramError as exc:
            if self.strict:
                raise
            log.warning("Не удалось отправить сообщение в %s: %s", chat_id, exc)
            return None

    def _session(self, chat_id: int) -> dict:
        return self.store.sessions.setdefault(str(chat_id), {})

    def _set_session(self, chat_id: int, **fields) -> dict:
        session = self.store.sessions.setdefault(str(chat_id), {})
        session.update(fields)
        return session

    def _clear_session(self, chat_id: int) -> None:
        self.store.sessions.pop(str(chat_id), None)

    def _remember_buyer(self, buyer_chat: int, result, order_id: str) -> None:
        if isinstance(result, dict) and result.get("message_id"):
            self.data["msgmap"][f"{buyer_chat}:{result['message_id']}"] = {
                "order_id": order_id,
            }
            self._trim_msgmap()

    def _trim_msgmap(self) -> None:
        msgmap = self.data.get("msgmap") or {}
        overflow = len(msgmap) - MAX_MSGMAP
        if overflow <= 0:
            return
        for key in list(msgmap)[:overflow]:
            msgmap.pop(key, None)

    def _find_order(self, order_id: str) -> dict | None:
        if not order_id:
            return None
        order = self.store.orders.get(str(order_id))
        if isinstance(order, dict):
            return order
        closed = self.store.closed.get(str(order_id))
        return closed if isinstance(closed, dict) else None

    @staticmethod
    def _proofs(order: dict) -> list[dict]:
        proofs = order.get("proofs")
        if isinstance(proofs, list) and proofs:
            return [item for item in proofs if isinstance(item, dict)]
        proof = order.get("proof")
        return [proof] if isinstance(proof, dict) else []

    def _orders_of_user(self, user_id) -> list[dict]:
        result: list[dict] = []
        for source in (self.store.orders, self.store.closed):
            for order in source.values():
                if isinstance(order, dict) and order.get("user_id") == user_id:
                    result.append(order)
        return result

    def _rate_limited(self, user_id: int) -> bool:
        limit, window = self.cfg.rate_limit_count, self.cfg.rate_limit_window
        if not limit or limit <= 0:
            return False
        now = self._now()
        hits = [stamp for stamp in self._hits.get(user_id, []) if now - stamp < window]
        hits.append(now)
        self._hits[user_id] = hits
        return len(hits) > limit

    def _is_admin(self, user: dict) -> bool:
        user_id = user.get("id")
        if user_id in self.cfg.admin_ids:
            return True
        if user_id in self.data["admins"]:
            return True
        username = (user.get("username") or "").lower()
        return bool(username) and username in self.cfg.all_admin_usernames

    def _register_admin(self, user: dict) -> bool:
        user_id = user.get("id")
        if not user_id:
            return False
        if user_id not in self.data["admins"]:
            self.data["admins"].append(user_id)
            self._save()
            log.info("Оператор подключён: @%s (id %s)", user.get("username"), user_id)
            return True
        return False

    def _admin_chat_ids(self) -> list[int]:
        result: list[int] = []
        for chat_id in list(self.cfg.admin_ids) + list(self.data["admins"]):
            if isinstance(chat_id, int) and chat_id not in result:
                result.append(chat_id)
        return result

    def handle_update(self, update: dict) -> None:
        try:
            if "callback_query" in update:
                self._on_callback(update["callback_query"])
            elif "message" in update:
                self._on_message(update["message"])
        except TelegramError as exc:
            if self.strict:
                raise
            log.warning("Ошибка Telegram API при обработке обновления: %s", exc)
        except Exception:
            if self.strict:
                raise
            log.exception("Необработанная ошибка в обновлении %s", update.get("update_id"))

    def _on_message(self, msg: dict) -> None:
        chat = msg.get("chat") or {}
        user = msg.get("from") or {}
        if chat.get("type") != "private" or not user or user.get("is_bot"):
            return

        chat_id = chat.get("id")
        text = (msg.get("text") or msg.get("caption") or "").strip()

        if self._is_admin(user):
            self._register_admin(user)
            self._on_admin_message(msg, text)
            return

        command = CMD_RE.match(text)
        if command:
            self._on_buyer_command(chat_id, user, command.group(1).lower())
            return

        if self._rate_limited(user.get("id") or chat_id):
            self._send(chat_id, T.rate_limited())
            return

        self._on_buyer_message(msg, text)

    def _on_buyer_command(self, chat_id: int, user: dict, command: str) -> None:
        if command == "start":
            self._clear_session(chat_id)
            self._send(chat_id, T.welcome(self.cfg, user.get("first_name")), T.welcome_keyboard())
            return
        if command == "help":
            self._send(chat_id, T.help_text(self.cfg))
            return
        if command == "info":
            self._send(chat_id, T.info_text(self.cfg), T.back_keyboard())
            return
        if command == "pay":
            self._start_order(chat_id, user)
            return
        if command == "cancel":
            self._cancel_buyer(chat_id, user)
            return
        if command == "status":
            self._send_status(chat_id, user)
            return
        self._send(chat_id, T.welcome(self.cfg, user.get("first_name")), T.welcome_keyboard())

    def _cancel_buyer(self, chat_id: int, user: dict) -> None:
        session = self._session(chat_id)
        step = session.get("step")
        order_id = session.get("order_id")
        order = self._find_order(order_id) if order_id else None

        if step == "sent" and isinstance(order, dict):
            self._close_or_refuse(order, chat_id)
            return

        self._clear_session(chat_id)
        if step in ("nick", "proof", "confirm"):
            self._send(chat_id, T.cancelled(), T.back_keyboard())
            self._save()
            return

        active = self._live_orders_of(user.get("id"))
        pending = [item for item in active if item.get("status") == "pending"]
        if pending:
            self._close_or_refuse(max(pending, key=lambda item: item.get("created_at") or 0), chat_id)
            return
        if active:
            self._send(chat_id, T.cancel_too_late(self.cfg, active[0].get("id")))
            return

        self._send(chat_id, T.nothing_to_cancel(self.cfg), T.back_keyboard())
        self._save()

    def _live_orders_of(self, user_id) -> list[dict]:
        return [
            order
            for order in self.store.orders.values()
            if isinstance(order, dict) and order.get("user_id") == user_id
        ]

    def _close_or_refuse(self, order: dict, chat_id: int) -> None:
        status = order.get("status")
        order_id = order.get("id")

        if status == "pending":
            self._clear_session(chat_id)
            self._finalize(order, "cancelled")
            self._send(chat_id, T.buyer_cancelled(self.cfg, order_id), T.back_keyboard())
            self._notify_cancelled(order)
            return

        if status == "awaiting_product":
            self._send(chat_id, T.cancel_too_late(self.cfg, order_id))
            return

        self._clear_session(chat_id)
        self._send(chat_id, T.already_closed(self.cfg, order_id), T.back_keyboard())
        self._save()

    def _notify_cancelled(self, order: dict) -> None:
        for admin_chat in self._admin_chat_ids():
            self._try_send(admin_chat, T.admin_buyer_cancelled(order["id"]))

    def _on_buyer_message(self, msg: dict, text: str) -> None:
        chat_id = msg["chat"]["id"]
        session = self._session(chat_id)
        step = session.get("step")

        if step == "nick":
            self._take_nick(chat_id, text)
            return
        if step == "proof":
            self._take_proof(chat_id, msg)
            return
        if step == "confirm":
            proof = self._extract_proof(msg)
            if proof and proof.get("kind") in ATTACHMENT_KINDS and proof.get("file_id"):
                self._add_proof(chat_id, proof)
                return
            self._send(chat_id, T.confirm_reminder(), T.preview_keyboard())
            return

        reply = msg.get("reply_to_message") or {}
        if reply.get("message_id"):
            record = self.data["msgmap"].get(f"{chat_id}:{reply['message_id']}")
            if isinstance(record, dict):
                self._relay_buyer_reply(msg, record.get("order_id", ""))
                return

        self._send(chat_id, T.outside_flow_hint(self.cfg), T.back_keyboard())

    def _start_order(self, chat_id: int, user: dict) -> None:
        self._set_session(chat_id, step="nick", started=self._now(), user_id=user.get("id"))
        self._send(chat_id, T.ask_nick(self.cfg), [[T.btn("✖️ Отмена", "cancel")]])
        self._save()

    def _guard_card(self, chat_id: int, text: str) -> bool:
        if looks_like_card(text, self._seller_digits):
            self._send(chat_id, T.card_warning(self.cfg))
            return True
        return False

    def _take_nick(self, chat_id: int, text: str) -> None:
        nick = " ".join((text or "").split())
        if not nick:
            self._send(chat_id, T.nick_empty())
            return
        if len(nick) > 64:
            self._send(chat_id, T.nick_too_long())
            return
        if self._guard_card(chat_id, nick):
            return

        self._set_session(chat_id, step="proof", nick=nick)
        self._send(chat_id, T.payment_step(self.cfg), [[T.btn("✖️ Отмена", "cancel")]])
        self._save()

    def _extract_proof(self, msg: dict) -> dict | None:
        caption = (msg.get("caption") or "").strip()
        photos = msg.get("photo") or []
        if photos:
            return {"kind": "photo", "file_id": photos[-1].get("file_id"), "caption": caption}
        document = msg.get("document")
        if document:
            return {
                "kind": "document",
                "file_id": document.get("file_id"),
                "name": document.get("file_name"),
                "caption": caption,
            }
        video = msg.get("video")
        if video:
            return {"kind": "video", "file_id": video.get("file_id"), "caption": caption}
        text = (msg.get("text") or caption).strip()
        if text and not text.startswith("/"):
            return {"kind": "text", "text": text[:1000]}
        return None

    def _take_proof(self, chat_id: int, msg: dict) -> None:
        proof = self._extract_proof(msg)
        if not proof or proof.get("kind") not in BUYER_PROOF_KINDS:
            self._send(chat_id, T.proof_required())
            return
        if proof.get("kind") == "text" and self._guard_card(chat_id, proof.get("text", "")):
            return
        if proof.get("kind") in ATTACHMENT_KINDS and not proof.get("file_id"):
            self._send(chat_id, T.proof_required())
            return

        self._set_session(chat_id, step="confirm", proof=proof, proofs=[proof])
        self._show_preview(chat_id)
        self._save()

    def _show_preview(self, chat_id: int, prefix: str = "") -> None:
        session = self._session(chat_id)
        proofs = session.get("proofs") or [session.get("proof") or {}]
        text = T.preview(self.cfg, session.get("nick", ""), proofs[0], len(proofs))
        self._send(chat_id, (prefix + "\n\n" if prefix else "") + text, T.preview_keyboard())

    def _add_proof(self, chat_id: int, proof: dict) -> None:
        session = self._session(chat_id)
        proofs = [item for item in session.get("proofs") or [] if isinstance(item, dict)]
        if len(proofs) >= MAX_PROOFS:
            self._send(chat_id, T.proof_limit(MAX_PROOFS), T.preview_keyboard())
            return
        proofs.append(proof)
        session["proofs"] = proofs
        session["proof"] = proofs[0]
        self._show_preview(chat_id, T.proof_added(len(proofs)))
        self._save()

    def _send_status(self, chat_id: int, user: dict) -> None:
        orders = self._orders_of_user(user.get("id"))
        if not orders:
            self._send(chat_id, T.no_orders_yet(), T.back_keyboard())
            return
        orders.sort(
            key=lambda item: item.get("updated_at") or item.get("created_at") or 0,
            reverse=True,
        )
        latest = orders[0]
        updated = self._fmt_time(latest["updated_at"]) if latest.get("updated_at") else ""
        self._send(
            chat_id,
            T.status_text(
                self.cfg,
                latest,
                self._fmt_time(latest.get("created_at", 0)),
                updated,
                len(orders),
            ),
            T.status_keyboard(latest),
        )

    def _submit(self, chat_id: int, user: dict) -> None:
        session = self._session(chat_id)
        if session.get("step") != "confirm" or not session.get("proof"):
            self._send(chat_id, T.nothing_to_send())
            return

        order_id = self.store.next_order_id()
        proofs = [
            item
            for item in (session.get("proofs") or [session.get("proof")])
            if isinstance(item, dict)
        ]
        order = {
            "id": order_id,
            "user_id": user.get("id"),
            "chat_id": chat_id,
            "username": user.get("username") or "",
            "name": user.get("first_name") or "",
            "nick": session.get("nick", ""),
            "proof": proofs[0],
            "proofs": proofs,
            "status": "pending",
            "created_at": self._now(),
            "admin_msgs": [],
        }
        order["text"] = T.order_card(self.cfg, order, self._fmt_time(order["created_at"]))
        self.store.orders[order_id] = order

        self._clear_session(chat_id)
        self._set_session(chat_id, step="sent", order_id=order_id)

        delivered = self._notify_admins(order)
        self._send(chat_id, T.order_sent(self.cfg, order_id))
        if not delivered:
            self._send(chat_id, T.no_admins(self.cfg))
        self._save()

    def _deliver_proof(self, chat_id: int, proof: dict, caption: str):
        kind = proof.get("kind")
        try:
            if kind == "photo":
                return self.api.call(
                    "sendPhoto",
                    chat_id=chat_id,
                    photo=proof.get("file_id"),
                    caption=caption,
                    parse_mode="HTML",
                )
            if kind == "document":
                return self.api.call(
                    "sendDocument",
                    chat_id=chat_id,
                    document=proof.get("file_id"),
                    caption=caption,
                    parse_mode="HTML",
                )
            if kind == "video":
                return self.api.call(
                    "sendVideo",
                    chat_id=chat_id,
                    video=proof.get("file_id"),
                    caption=caption,
                    parse_mode="HTML",
                )
        except TelegramError as exc:
            log.warning("Вложение не доставлено (%s): %s", kind, exc)
            return self._send(chat_id, f"{caption}\n\n⚠️ Вложение не удалось переслать.")
        if kind == "text":
            return self._send(
                chat_id,
                f"{caption}\n\n<blockquote>{html.escape(proof.get('text', ''))}</blockquote>",
            )
        return None

    def _notify_admins(self, order: dict) -> bool:
        admins = self._admin_chat_ids()
        if not admins:
            log.error(
                "Нет подключённых операторов: заявка #%s сохранена, но не доставлена",
                order["id"],
            )
            return False

        keyboard = T.order_keyboard(order["id"])
        proofs = self._proofs(order)
        delivered = False
        for chat_id in admins:
            try:
                result = self._send(chat_id, order["text"], keyboard)
                if isinstance(result, dict) and result.get("message_id"):
                    order["admin_msgs"].append([chat_id, result["message_id"]])

                for index, proof in enumerate(proofs):
                    self._deliver_proof(
                        chat_id, proof, T.proof_caption(order["id"], index, len(proofs))
                    )
                delivered = True
            except TelegramError as exc:
                log.warning("Оператор %s недоступен: %s", chat_id, exc)
        self._save()
        return delivered

    def _on_callback(self, callback: dict) -> None:
        user = callback.get("from") or {}
        data = callback.get("data") or ""
        message = callback.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id") or user.get("id")

        try:
            self.api.call("answerCallbackQuery", callback_query_id=callback.get("id"))
        except TelegramError as exc:
            log.debug("answerCallbackQuery: %s", exc)

        if data in ("pay", "restart"):
            self._start_order(chat_id, user)
            return
        if data == "help":
            self._send(chat_id, T.help_text(self.cfg))
            return
        if data == "info":
            self._send(chat_id, T.info_text(self.cfg), T.back_keyboard())
            return
        if data == "status":
            self._send_status(chat_id, user)
            return
        if data == "cancel":
            if self._is_admin(user):
                self._cancel_admin_step(chat_id)
                return
            self._cancel_buyer(chat_id, user)
            return
        if data == "confirm":
            self._submit(chat_id, user)
            return
        if data in ("orders", "history", "stats", "link"):
            if not self._is_admin(user):
                self._send(chat_id, T.admins_only())
                return
            if data == "orders":
                self._send_pending(chat_id)
            elif data == "history":
                self._send_history(chat_id)
            elif data == "stats":
                self._send(
                    chat_id,
                    T.stats_text(self.cfg, self.store.stats(), self._admin_chat_ids()),
                )
            else:
                self._send(chat_id, T.link_text(self.cfg))
            return

        action, _, order_id = data.partition(":")
        if action in ("acc", "rej", "unacc", "chat") and order_id:
            self._admin_action(action, order_id, user, chat_id)
            return
        if action == "proof" and order_id:
            if not self._is_admin(user):
                self._send(chat_id, T.admins_only())
                return
            self._send_proof_to(chat_id, order_id)
            return

        log.debug("Неизвестный callback: %s", data)

    def _admin_action(self, action: str, order_id: str, user: dict, chat_id: int) -> None:
        if not self._is_admin(user):
            self._send(chat_id, T.admins_only())
            return

        order = self._find_order(order_id)
        if not isinstance(order, dict):
            self._send(chat_id, T.order_missing(order_id))
            return

        if action == "acc":
            if order.get("status") == "accepted":
                self._send(chat_id, T.already_done(order_id))
                return
            if order.get("status") in ("cancelled", "rejected"):
                self._send(chat_id, T.already_closed(self.cfg, order_id))
                return
            self._set_status(order, "awaiting_product")
            self._set_session(chat_id, step="product", order_id=order_id)
            self._send(
                chat_id,
                T.ask_product_photo(self.cfg, order_id),
                [[T.btn("✖️ Отмена", f"unacc:{order_id}")]],
            )
        elif action == "rej":
            if order.get("status") == "rejected":
                self._send(chat_id, T.already_rejected(order_id))
                return
            if order.get("status") in ("cancelled", "accepted"):
                self._send(chat_id, T.already_closed(self.cfg, order_id))
                return
            self._clear_session(chat_id)
            self._finalize(order, "rejected")
            self._try_send(order["chat_id"], T.buyer_rejected(self.cfg, order_id))
            self._send(chat_id, f"❌ Заявка #{order_id} отклонена. Покупатель уведомлён.")
            return
        elif action == "unacc":
            if order.get("status") != "awaiting_product":
                self._send(chat_id, "Эту заявку уже нельзя вернуть в ожидание.")
                return
            self._clear_session(chat_id)
            self._set_status(order, "pending")
            self._send(chat_id, T.order_cancelled_accept(order_id))
        else:
            self._set_session(chat_id, step="chat", order_id=order_id)
            self._send(chat_id, T.ask_chat_message(order_id), [[T.btn("✖️ Закончить", "cancel")]])
        self._save()

    def _set_status(self, order: dict, status: str, final: bool = False) -> None:
        order["status"] = status
        order["updated_at"] = self._now()
        suffix = "\n\n" + T.status_line(status, self._fmt_time(order["updated_at"]))
        for entry in order.get("admin_msgs", []):
            try:
                chat_id, message_id = entry
            except (TypeError, ValueError):
                continue
            params = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": order.get("text", "") + suffix,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if final:
                params["reply_markup"] = {"inline_keyboard": T.done_keyboard(order["id"])}
            try:
                self.api.call("editMessageText", **params)
            except TelegramError as exc:
                log.debug("Не удалось обновить карточку заявки #%s: %s", order.get("id"), exc)

    def _finalize(self, order: dict, status: str) -> None:
        order_id = str(order.get("id"))
        self._set_status(order, status, final=True)
        order["status"] = status
        kept = self.store.archive(order, keep=self.cfg.keep_closed)
        self.store.clear_sessions_for(order_id)
        log.info(
            "Заявка #%s закрыта (%s): карточка удалена, история %s/%s, переписка %s",
            order_id,
            status,
            len(self.store.closed),
            self.cfg.keep_closed,
            "оставлена" if kept else "удалена",
        )
        self._save()

    def _history_rows(self) -> list[dict]:
        items = [item for item in self.store.closed.values() if isinstance(item, dict)]
        items.sort(
            key=lambda item: item.get("updated_at") or item.get("created_at") or 0,
            reverse=True,
        )
        return [
            {
                "id": item.get("id"),
                "nick": item.get("nick"),
                "name": item.get("name"),
                "status": item.get("status"),
                "when": self._fmt_time(item.get("updated_at") or item.get("created_at") or 0),
            }
            for item in items[:MAX_CHAT_HISTORY]
        ]

    def _send_history(self, chat_id: int) -> None:
        rows = self._history_rows()
        self._send(chat_id, T.history_text(self.cfg, rows), T.history_keyboard(rows) or None)

    def _send_proof_to(self, chat_id: int, order_id: str) -> None:
        order = self._find_order(order_id)
        if not isinstance(order, dict):
            self._send(chat_id, T.order_missing(order_id))
            return

        proofs = self._proofs(order)
        if not proofs:
            self._send(chat_id, T.proof_missing(order_id))
            return

        self._send(chat_id, T.proof_header(order_id, order.get("status") or ""))
        for index, proof in enumerate(proofs):
            self._deliver_proof(chat_id, proof, T.proof_caption(order_id, index, len(proofs)))

    def _on_admin_message(self, msg: dict, text: str) -> None:
        chat_id = msg["chat"]["id"]
        session = self._session(chat_id)

        command = CMD_RE.match(text)
        if command:
            self._on_admin_command(chat_id, msg, command.group(1).lower(), (command.group(2) or "").strip())
            return

        step = session.get("step")
        order_id = session.get("order_id")
        if step == "product" and order_id:
            self._take_product_photo(chat_id, msg, order_id)
            return
        if step == "chat" and order_id:
            self._send_chat_message(chat_id, order_id, msg)
            return

        self._send(chat_id, T.admin_hint())

    def _take_product_photo(self, chat_id: int, msg: dict, order_id: str) -> None:
        order = self._find_order(order_id)
        if not isinstance(order, dict):
            self._clear_session(chat_id)
            self._send(chat_id, T.order_missing(order_id))
            return
        if order.get("status") == "accepted":
            self._clear_session(chat_id)
            self._send(chat_id, T.already_done(order_id))
            return
        if order.get("status") in ("cancelled", "rejected"):

            self._clear_session(chat_id)
            self._send(chat_id, T.already_closed(self.cfg, order_id))
            return

        proof = self._extract_proof(msg)
        if not proof or proof.get("kind") not in PRODUCT_KINDS or not proof.get("file_id"):
            self._send(chat_id, T.product_photo_required(self.cfg, order_id))
            return

        order["product"] = proof
        order["product_text"] = (proof.get("caption") or "").strip()
        order["delivered_at"] = self._now()
        delivered = self._send_product(order)
        self._finalize(order, "accepted")
        self._clear_session(chat_id)
        self._send(chat_id, T.product_sent(self.cfg, order_id, delivered))
        self._save()

    def _send_product(self, order: dict) -> bool:
        buyer = order.get("chat_id")
        product = order.get("product") or {}
        text = (order.get("product_text") or "").strip()
        is_document = product.get("kind") == "document"
        method = "sendDocument" if is_document else "sendPhoto"
        key = "document" if is_document else "photo"
        try:
            if text:

                result = self.api.call(
                    method,
                    chat_id=buyer,
                    **{key: product.get("file_id")},
                    caption=text[:1024],
                )
                self._remember_buyer(buyer, result, order["id"])
                system = self._send(buyer, T.buyer_delivered(self.cfg, order["id"]))
                self._remember_buyer(buyer, system, order["id"])
            else:
                result = self.api.call(
                    method,
                    chat_id=buyer,
                    **{key: product.get("file_id")},
                    caption=T.buyer_delivered(self.cfg, order["id"]),
                    parse_mode="HTML",
                )
                self._remember_buyer(buyer, result, order["id"])
            return True
        except TelegramError as exc:
            log.warning("Материал покупателю %s не доставлен: %s", buyer, exc)
            self._try_send(
                buyer,
                T.buyer_delivered(self.cfg, order["id"])
                + "\n\n⚠️ Фото не удалось передать — оператор пришлёт его вручную.",
            )
            return False

    def _send_chat_message(self, admin_chat: int, order_id: str, msg: dict) -> None:
        order = self._find_order(order_id)
        if not isinstance(order, dict):
            self._clear_session(admin_chat)
            self._send(admin_chat, T.order_missing(order_id))
            return
        buyer = order.get("chat_id")
        try:
            result = self.api.call(
                "copyMessage",
                chat_id=buyer,
                from_chat_id=admin_chat,
                message_id=msg.get("message_id"),
            )
            self._remember_buyer(buyer, result, order_id)
            self._send(admin_chat, T.chat_sent())
        except TelegramError as exc:
            log.warning("Сообщение по заявке #%s не доставлено: %s", order_id, exc)
            self._send(admin_chat, T.chat_failed())

    def _relay_buyer_reply(self, msg: dict, order_id: str) -> None:
        buyer_chat = msg["chat"]["id"]
        admins = self._admin_chat_ids()
        if not admins:
            self._send(buyer_chat, T.no_admins(self.cfg))
            return

        delivered = False
        for admin_chat in admins:
            try:
                self._send(admin_chat, T.buyer_reply_header(order_id), T.reply_button(order_id))
                self.api.call(
                    "copyMessage",
                    chat_id=admin_chat,
                    from_chat_id=buyer_chat,
                    message_id=msg.get("message_id"),
                )
                delivered = True
            except TelegramError as exc:
                log.warning("Ответ покупателя не доставлен оператору %s: %s", admin_chat, exc)

        self._send(buyer_chat, T.reply_forwarded() if delivered else T.no_admins(self.cfg))
        self._save()

    def _send_pending(self, chat_id: int) -> None:
        pending = [
            order
            for order in self.store.orders.values()
            if isinstance(order, dict) and order.get("status") in ("pending", "awaiting_product")
        ]
        pending.sort(key=lambda item: item.get("created_at", 0))
        keyboard = T.pending_keyboard(pending) if pending else None
        self._send(chat_id, T.orders_list(self.cfg, pending), keyboard)

    def _on_admin_command(self, chat_id: int, msg: dict, command: str, argument: str) -> None:
        if command == "start":
            self._clear_session(chat_id)
            self._register_admin(msg.get("from") or {})
            self._send(
                chat_id,
                T.admin_welcome(self.cfg, (msg.get("from") or {}).get("first_name")),
                T.admin_welcome_keyboard(),
            )
            return
        if command == "id":
            self._send(
                chat_id,
                f"🆔 Твой chat_id: <code>{chat_id}</code>\n"
                f"Username: @{html.escape((msg.get('from') or {}).get('username') or '—')}",
            )
            return
        if command == "orders":
            self._send_pending(chat_id)
            return
        if command == "history":
            self._send_history(chat_id)
            return
        if command == "stats":
            self._send(chat_id, T.stats_text(self.cfg, self.store.stats(), self._admin_chat_ids()))
            return
        if command == "link":
            self._send(chat_id, T.link_text(self.cfg))
            return
        if command == "cancel":
            self._cancel_admin_step(chat_id)
            return
        self._send(chat_id, T.unknown_command(self.cfg))

    def _cancel_admin_step(self, chat_id: int) -> None:
        session = self._session(chat_id)
        order_id = session.get("order_id")
        step = session.get("step")
        self._clear_session(chat_id)

        if step == "product" and order_id:
            order = self._find_order(order_id)
            if isinstance(order, dict) and order.get("status") == "awaiting_product":
                self._set_status(order, "pending")
                self._send(chat_id, T.order_cancelled_accept(order_id))
                self._save()
                return
        if step == "chat":
            self._send(chat_id, T.chat_closed())
            return
        self._send(chat_id, "Ок, действие отменено.")
