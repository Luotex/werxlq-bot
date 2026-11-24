from __future__ import annotations

import html
import os

def esc(value) -> str:
    return html.escape(str(value or ""), quote=False)

def btn(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}

APPLY_BUTTON = "🛒 Купить сигну"
INFO_BUTTON = "ℹ️ О боте"
HELP_BUTTON = "❓ Как это работает"
WRITE_BUTTON = "✍️ Написать по заявке"
STATUS_BUTTON = "📄 Статус заявки"
CANCEL_BUTTON = "✖️ Отменить заявку"
PROOF_BUTTON = "📎 Доказательство"
HISTORY_BUTTON = "📜 История"
ORDERS_BUTTON = "📋 Заявки в работе"
STATS_BUTTON = "📊 Статистика"
LINK_BUTTON = "🔗 Ссылка для покупателей"

def card_block(cfg) -> str:
    lines = [
        "💳 <b>Реквизиты для оплаты</b>",
        f"Банк: <b>{esc(cfg.bank)}</b>",
        f"Получатель: <b>{esc(cfg.card_holder)}</b>",
        f"Карта: <code>{esc(cfg.card_number)}</code>",
    ]
    if cfg.price:
        lines.append(f"Сумма: <b>{esc(cfg.price)}</b>")
    return "\n".join(lines)

def welcome(cfg, name: str) -> str:
    intro = esc(cfg.intro) or "Это бот для заявок."
    offer = f"Здесь можно купить {esc(cfg.product)}." if cfg.product else "Здесь можно сделать заказ."
    return (
        f"👋 Привет{f', {esc(name)}' if name else ''}!\n\n"
        f"{intro}\n\n"
        f"{offer}\n"
        f"Нажми «{APPLY_BUTTON}», пришли ник — бот покажет реквизиты и примет заявку.\n\n"
        f"Статус своей заявки смотри кнопкой «{STATUS_BUTTON}», "
        f"передумал — «{CANCEL_BUTTON}»."
    )

def welcome_keyboard() -> list:
    return [
        [btn(APPLY_BUTTON, "pay")],
        [btn(STATUS_BUTTON, "status"), btn(CANCEL_BUTTON, "cancel")],
        [btn(INFO_BUTTON, "info"), btn(HELP_BUTTON, "help")],
    ]

def back_keyboard() -> list:
    return [
        [btn(APPLY_BUTTON, "pay")],
        [btn(STATUS_BUTTON, "status"), btn(CANCEL_BUTTON, "cancel")],
        [btn(INFO_BUTTON, "info")],
    ]

def info_text(cfg) -> str:
    lines = ["ℹ️ <b>О боте</b>", ""]
    if cfg.bot_username:
        lines.append(f"🤖 Бот: @{esc(cfg.bot_username)}")
    if cfg.bot_created:
        lines.append(f"📅 Создан: {esc(cfg.bot_created)}")
    if cfg.bot_developer:
        lines.append(f"👨‍💻 Разработчик: @{esc(cfg.bot_developer)}")
    if cfg.bot_for:
        lines.append(f"🎯 Для: {esc(cfg.bot_for)}")

    custom = (os.environ.get("BOT_INFO") or "").strip().replace("\\n", "\n")
    if custom:
        lines.append(custom)
    elif cfg.product:
        lines.append(f"🛒 Купить: {esc(cfg.product)}")
    return "\n".join(lines)

def help_text(cfg) -> str:
    return (
        "ℹ️ <b>Как это работает</b>\n\n"
        "1. Нажми «" + APPLY_BUTTON + "».\n"
        "2. Пришли ник, на который оформляешь заказ.\n"
        "3. Бот покажет реквизиты — переведи оплату.\n"
        "4. Пришли подтверждение: фото чека или текст с номером перевода.\n"
        "5. Оператор проверит оплату и пришлёт материал в этот чат.\n\n"
        "После отправки бот пришлёт тебе копию подтверждения оплаты — она останется "
        "в чате, ею можно подтвердить заявку, если что-то пойдёт не так.\n\n"
        "Кнопки в меню:\n"
        f"• «{STATUS_BUTTON}» — на каком этапе заявка;\n"
        f"• «{CANCEL_BUTTON}» — отменить заявку, пока оператор её не взял.\n\n"
        "Команды:\n"
        "/cancel — отменить текущую заявку\n"
        "/status — статус последней заявки\n\n"
        "⚠️ Сообщения вне заявки оператору не отправляются. Ответить оператору "
        "можно реплаем на его сообщение."
    )

def outside_flow_hint(cfg) -> str:
    return (
        f"ℹ️ Чтобы оформить заявку, нажми «{APPLY_BUTTON}».\n\n"
        "Ответить оператору можно реплаем (свайп по его сообщению → «Ответить»). "
        "Остальные сообщения вне заявки оператору не уходят."
    )

def ask_nick(cfg) -> str:
    return (
        "✍️ <b>Шаг 1 из 3 — ник</b>\n\n"
        "Отправь ник, на который оформляешь заказ (одно сообщение, до 64 символов)."
    )

def nick_empty() -> str:
    return "Ник не может быть пустым. Напиши его текстом, например: <code>werxlq_2026</code>"

def nick_too_long() -> str:
    return "Слишком длинный ник (максимум 64 символа). Пришли покороче."

def payment_step(cfg) -> str:
    return (
        "💳 <b>Шаг 2 из 3 — оплата</b>\n\n"
        f"{card_block(cfg)}\n\n"
        "Переведи оплату по реквизитам и пришли подтверждение:\n"
        "фото чека или текст с номером перевода.\n"
        "Фото можно прислать несколько — они уйдут оператору вместе с заявкой."
    )

def proof_required() -> str:
    return "Пришли подтверждение оплаты: фото чека или текст с номером перевода."

def proof_limit(limit: int) -> str:
    return (
        f"Уже приложено {limit} подтверждений — этого достаточно.\n"
        "Нажми «✅ Отправить заявку» под карточкой выше или «✖️ Отмена»."
    )

def proof_added(count: int) -> str:
    return f"📎 Добавлено, всего вложений: {count}. Можно добавить ещё или отправить заявку."

def card_warning(cfg) -> str:
    return (
        "⚠️ Похоже, ты прислал номер банковской карты.\n"
        "Для заявки это не нужно и небезопасно — пришли фото чека, "
        "номер перевода или последние 4 цифры."
    )

def proof_desc(proof: dict, count: int = 1) -> str:
    kind = (proof or {}).get("kind")
    if kind == "photo":
        base = "фото чека"
    elif kind == "document":
        name = (proof or {}).get("name")
        base = f"файл ({esc(name)})" if name else "файл с чеком"
    elif kind == "video":
        base = "видео-подтверждение"
    else:
        text = ((proof or {}).get("text") or "").strip()
        if len(text) > 80:
            text = text[:77] + "…"
        base = f"«{esc(text)}»" if text else "не указано"
    if count > 1:
        return f"{base} +{count - 1}"
    return base

def preview(cfg, nick: str, proof: dict, count: int = 1) -> str:
    extra = (
        f"📎 Вложений: <b>{count}</b> — можно добавить ещё фото, они тоже уйдут оператору."
        if count > 1
        else "📎 Можно прислать ещё фото чека — они уйдут оператору вместе с заявкой."
    )
    return (
        "🔍 <b>Шаг 3 из 3 — проверь заявку</b>\n\n"
        f"🎮 Ник: <b>{esc(nick)}</b>\n"
        f"💳 Оплата: {proof_desc(proof, count)}\n\n"
        f"{extra}\n\n"
        "Если всё верно — жми «✅ Отправить заявку»."
    )

def preview_keyboard() -> list:
    return [[btn("✅ Отправить заявку", "confirm")], [btn("✖️ Отмена", "cancel")]]

def order_sent(cfg, order_id: str) -> str:
    return (
        f"✅ Заявка <b>#{esc(order_id)}</b> отправлена.\n\n"
        f"Ожидай: @{esc(cfg.admin_username)} проверит оплату и пришлёт "
        f"{esc(cfg.product) or 'заказ'} в этот чат.\n\n"
        f"Следить за заявкой: кнопка «{STATUS_BUTTON}» в меню.\n"
        f"Передумал — «{CANCEL_BUTTON}», но только пока оператор её не взял.\n\n"
        "📎 Ниже — копия твоего подтверждения оплаты. Она останется в этом чате: "
        "если что-то пойдёт не так, будет чем подтвердить заявку."
    )


def proof_caption_buyer(order_id: str, index: int = 0, total: int = 1) -> str:
    suffix = f" · фото {index + 1} из {total}" if total > 1 else ""
    return f"Твоё подтверждение оплаты · заявка #{esc(order_id)}{suffix}"


def buyer_proof_header(order_id: str, status: str = "") -> str:
    label = status_label({"status": status}) if status else ""
    tail = f"\nСтатус: {label}" if label else ""
    return (
        f"📎 <b>Твоё подтверждение по заявке #{esc(order_id)}</b>{tail}\n\n"
        "Копия остаётся в чате: по ней видно, что заявка оформлена и оплата отправлена."
    )


def buyer_proof_missing() -> str:
    return (
        "По этой заявке вложение не сохранилось — похоже, подтверждение было текстом.\n"
        "Пролистай переписку выше, там есть твоё сообщение."
    )

def nothing_to_send() -> str:
    return f"Сейчас нечего отправлять. Нажми «{APPLY_BUTTON}», чтобы начать заново."

def confirm_reminder() -> str:
    return "Нажми «✅ Отправить заявку» или «✖️ Отмена» под карточкой выше."

def cancelled() -> str:
    return f"✖️ Заявка отменена. Когда будешь готов — нажми «{APPLY_BUTTON}»."

def nothing_to_cancel(cfg) -> str:
    return (
        "Отменять пока нечего: активной заявки нет.\n"
        f"Оформить новую — «{APPLY_BUTTON}», проверить статус — «{STATUS_BUTTON}»."
    )

def status_label(order: dict) -> str:
    return {
        "pending": "🕓 ожидает проверки оплаты",
        "awaiting_product": "⏳ оплата подтверждена, оператор готовит материал",
        "accepted": "✅ выполнена, материал отправлен",
        "rejected": "❌ отклонена",
        "cancelled": "🚫 отменена",
    }.get((order or {}).get("status", "pending"), str((order or {}).get("status", "")))

def status_text(cfg, order: dict, when: str, updated: str = "", total: int = 1) -> str:
    status = (order or {}).get("status", "pending")
    lines = [
        f"📄 <b>Заявка #{esc(order.get('id'))}</b>",
        f"🎮 Ник: {esc(order.get('nick'))}",
        f"Статус: {status_label(order)}",
        f"Создана: {esc(when)}",
    ]
    if updated:
        lines.append(f"Обновлена: {esc(updated)}")
    if total > 1:
        lines.append(f"Всего твоих заявок: {total}")

    hint = {
        "pending": "Оператор ещё не взял заявку. Её можно отменить кнопкой ниже.",
        "awaiting_product": "Оператор уже подтвердил оплату и готовит материал. "
                            "Отменить такую заявку нельзя — напиши ему реплаем.",
        "accepted": "Готово, спасибо за покупку!",
        "rejected": "Оплату подтвердить не удалось. Можно оформить заявку заново с чеком.",
        "cancelled": "Заявка отменена. Можно оформить новую — реквизиты те же.",
    }.get(status, "")
    if hint:
        lines.extend(["", hint])
    return "\n".join(lines)

def status_keyboard(order: dict) -> list:
    status = (order or {}).get("status", "pending")
    if status == "pending":
        return [
            [btn("📎 Моё доказательство", "myproof"), btn(CANCEL_BUTTON, "cancel")],
            [btn("🔄 Обновить статус", "status")],
        ]
    if status == "awaiting_product":
        return [[btn("📎 Моё доказательство", "myproof"), btn("🔄 Обновить статус", "status")]]
    return [
        [btn("📎 Моё доказательство", "myproof")],
        [btn(APPLY_BUTTON, "pay")],
    ]

def no_orders_yet() -> str:
    return f"У тебя пока нет заявок. Нажми «{APPLY_BUTTON}», чтобы создать первую."

def rate_limited() -> str:
    return "⏳ Слишком много сообщений подряд. Подожди минуту и напиши снова."

def no_admins(cfg) -> str:
    return (
        "⚠️ Оператор ещё не подключён к боту.\n"
        f"Попроси @{esc(cfg.admin_username)} открыть бота и нажать /start — "
        "после этого заявки начнут доходить."
    )

def buyer_delivered(cfg, order_id: str) -> str:
    return (
        f"✅ <b>Оплата подтверждена</b>\n\n"
        f"Заявка #{esc(order_id)} выполнена. Материал — выше.\n"
        "Спасибо за покупку!"
    )

def buyer_rejected(cfg, order_id: str) -> str:
    return (
        f"❌ <b>Заявка #{esc(order_id)} отклонена</b>\n\n"
        "Оплату не удалось подтвердить. Если считаешь, что это ошибка — "
        "оформи заявку заново с чеком, оператор проверит ещё раз."
    )

def buyer_cancelled(cfg, order_id: str) -> str:
    return (
        f"❌ <b>Заявка #{esc(order_id)} отменена</b>\n\n"
        "Если передумаешь — оформи новую, реквизиты те же."
    )

def cancel_too_late(cfg, order_id: str) -> str:
    return (
        f"⏳ Заявку #{esc(order_id)} уже подтвердил оператор — отменить её нельзя.\n\n"
        "Он готовит материал. Если что-то не так — ответь реплаем на его сообщение."
    )

def already_closed(cfg, order_id: str) -> str:
    return f"Заявка #{esc(order_id)} уже закрыта, отменять нечего."

def admin_buyer_cancelled(order_id: str) -> str:
    return (
        f"🚫 <b>Покупатель отменил заявку #{esc(order_id)}</b>\n\n"
        "Обрабатывать её больше не нужно — карточка закрыта."
    )

def reply_forwarded() -> str:
    return "📨 Передано оператору."

def buyer_got_reply() -> str:
    return "💬 Оператор ответил на твоё сообщение."

def order_card(cfg, order: dict, when: str) -> str:
    username = order.get("username")
    who = f"@{esc(username)}" if username else f"id {order.get('user_id')}"
    proofs = order.get("proofs") or [order.get("proof") or {}]
    count = len([item for item in proofs if item])
    lines = [
        f"🧾 <b>Заявка #{esc(order.get('id'))}</b>",
        f"🎮 Ник: <b>{esc(order.get('nick'))}</b>",
        f"👤 От: {esc(order.get('name'))} ({who})",
        f"💬 Чат покупателя: <a href=\"tg://user?id={esc(order.get('user_id'))}\">открыть</a>",
        f"💳 Оплата: {proof_desc(order.get('proof') or {}, count)}",
    ]
    if (order.get("proof") or {}).get("caption"):
        caption = (order.get("proof") or {}).get("caption") or ""
        if len(caption) > 120:
            caption = caption[:117] + "…"
        lines.append(f"📝 К чеку: {esc(caption)}")
    lines.append(f"🕐 {esc(when)}")
    return "\n".join(lines)

def order_keyboard(order_id: str) -> list:
    return [
        [btn("✅ Подтвердить", f"acc:{order_id}"), btn("❌ Отклонить", f"rej:{order_id}")],
        [btn(PROOF_BUTTON, f"proof:{order_id}"), btn(WRITE_BUTTON, f"chat:{order_id}")],
    ]

def done_keyboard(order_id: str) -> list:
    return [
        [btn(PROOF_BUTTON, f"proof:{order_id}")],
        [btn(WRITE_BUTTON, f"chat:{order_id}")],
    ]

def proof_caption(order_id: str, index: int = 0, total: int = 1) -> str:
    suffix = f" · файл {index + 1} из {total}" if total > 1 else ""
    return f"Подтверждение оплаты к заявке #{esc(order_id)}{suffix}"

def proof_header(order_id: str, status: str = "") -> str:
    label = status_label({"status": status}) if status else ""
    tail = f" · {label}" if label else ""
    return f"📎 <b>Доказательство оплаты по заявке #{esc(order_id)}</b>{tail}"

def proof_missing(order_id: str) -> str:
    return (
        f"По заявке #{esc(order_id)} доказательство не сохранено "
        "(например, покупатель прислал только текст, а запись уже очищена)."
    )

def status_line(status: str, when: str) -> str:
    return {
        "accepted": f"✅ Выполнено: {esc(when)}",
        "rejected": f"❌ Отклонено: {esc(when)}",
        "cancelled": f"🚫 Отменено покупателем: {esc(when)}",
        "awaiting_product": f"⏳ Ожидает фото с материалом: {esc(when)}",
        "pending": f"🕓 Ожидает проверки: {esc(when)}",
    }.get(status, status)

def admin_welcome(cfg, name: str) -> str:
    return (
        f"🛠 <b>Панель оператора</b>\n\n"
        f"Привет, {esc(name) or 'оператор'}! Сюда приходят заявки.\n\n"
        "• Заявка приходит карточкой: ник, покупатель и подтверждение оплаты.\n"
        "• «✅ Подтвердить» → пришли фото с материалом; подпись к фото "
        "тоже уйдёт покупателю.\n"
        f"• «{PROOF_BUTTON}» — посмотреть фото чека от покупателя в любой момент "
        "(и в новых, и в закрытых заявках).\n"
        "• «✍️ Написать по заявке» — переписка с покупателем по этой заявке.\n"
        "• «❌ Отклонить» — покупатель получит отказ.\n\n"
        f"«{ORDERS_BUTTON}» — что ждёт действия, «{HISTORY_BUTTON}» — закрытые "
        f"заявки, «{STATS_BUTTON}» — сводка, «{LINK_BUTTON}» — что отправить покупателю.\n\n"
        "Посторонние сообщения покупателей сюда НЕ пересылаются — только заявки "
        "и их ответы на твои сообщения.\n\n"
        "Команды:\n"
        "/id — твой chat_id\n"
        "/orders — заявки в ожидании\n"
        "/history — закрытые заявки\n"
        "/stats — статистика\n"
        "/link — ссылка на бота для покупателей\n"
        "/cancel — закончить переписку / отменить действие"
    )

def admin_hint() -> str:
    return (
        "Чтобы ответить покупателю, нажми «✍️ Написать по заявке» в карточке заявки.\n"
        "Команды: /start • /orders • /history • /stats • /link"
    )

def admins_only() -> str:
    return "Эта кнопка доступна только оператору."

def order_missing(order_id: str) -> str:
    return f"Заявка #{esc(order_id)} не найдена."

def ask_product_photo(cfg, order_id: str) -> str:
    return (
        f"📷 <b>Заявка #{esc(order_id)}</b>\n\n"
        "Пришли фото с материалом. Подпись к фото тоже уйдёт покупателю — "
        "можешь написать в ней пару слов или условия.\n\n"
        "Отмена — кнопка ниже."
    )

def product_photo_required(cfg, order_id: str) -> str:
    return (
        f"Нужно именно фото с материалом (или файл-картинка) для заявки #{esc(order_id)}.\n"
        "Подпись к фото тоже дойдёт покупателю. Отправь фото, либо нажми «✖️ Отмена»."
    )

def product_sent(cfg, order_id: str, delivered: bool) -> str:
    if delivered:
        return (
            f"✅ Фото отправлено покупателю. Заявка #{esc(order_id)} закрыта "
            "и перенесена в историю.\n"
            "Хочешь что-то добавить — жми «✍️ Написать по заявке»."
        )
    return (
        f"⚠️ Покупателю не удалось доставить фото по заявке #{esc(order_id)} "
        "(возможно, он заблокировал бота). Отправь материал вручную."
    )

def ask_chat_message(order_id: str) -> str:
    return (
        f"✍️ <b>Переписка по заявке #{esc(order_id)}</b>\n\n"
        "Напиши сообщение покупателю: текст, фото с подписью или файл — "
        "всё уйдёт ему в чат.\n"
        "Можно отправлять сколько угодно сообщений подряд.\n"
        "Закончить: /cancel"
    )

def chat_sent() -> str:
    return "✅ Отправлено покупателю."

def chat_closed() -> str:
    return "Переписка завершена. Карточка заявки — в чате выше."

def chat_failed() -> str:
    return "⚠️ Не удалось отправить: покупатель мог заблокировать бота."

def buyer_reply_header(order_id: str) -> str:
    return (
        f"💬 <b>Ответ покупателя</b> по заявке #{esc(order_id)}\n\n"
        "Нажми «✍️ Ответить», чтобы продолжить переписку."
    )

def reply_button(order_id: str) -> list:
    return [[btn("✍️ Ответить", f"chat:{order_id}")]]

def order_cancelled_accept(order_id: str) -> str:
    return f"↩️ Подтверждение снято: заявка #{esc(order_id)} снова в ожидании."

def already_done(order_id: str) -> str:
    return f"Заявка #{esc(order_id)} уже выполнена."

def already_rejected(order_id: str) -> str:
    return f"Заявка #{esc(order_id)} уже отклонена."

def orders_list(cfg, orders: list) -> str:
    if not orders:
        return "📭 Заявок в ожидании нет."
    lines = [f"🕓 <b>В работе: {len(orders)}</b>", ""]
    for order in orders[:30]:
        username = order.get("username")
        who = f"@{esc(username)}" if username else f"id {order.get('user_id')}"
        state = "ждёт фото" if order.get("status") == "awaiting_product" else "ждёт проверки"
        lines.append(f"#{esc(order.get('id'))} · <b>{esc(order.get('nick'))}</b> · {who} · {state}")
    lines.append("")
    lines.append("Подтверждай и отклоняй кнопками ниже:")
    return "\n".join(lines)

def pending_keyboard(orders: list) -> list:
    rows = []
    for order in orders[:20]:
        order_id = order.get("id", "")
        if not order_id:
            continue
        rows.append([
            btn(f"✅ #{order_id}", f"acc:{order_id}"),
            btn(f"❌ #{order_id}", f"rej:{order_id}"),
        ])
        rows.append([
            btn(f"{PROOF_BUTTON} #{order_id}", f"proof:{order_id}"),
            btn(f"{WRITE_BUTTON} #{order_id}", f"chat:{order_id}"),
        ])
    return rows

def history_empty() -> str:
    return "📜 История пока пуста — закрытых заявок нет."

def history_text(cfg, rows: list) -> str:
    if not rows:
        return history_empty()
    lines = [f"📜 <b>Закрытые заявки: {len(rows)}</b>", ""]
    for row in rows:
        lines.append(
            f"#{esc(row.get('id'))} · {status_label({'status': row.get('status')})}\n"
            f"    🎮 {esc(row.get('nick'))} · {esc(row.get('name') or '—')} · {esc(row.get('when'))}"
        )
    lines.append("")
    lines.append(f"«{PROOF_BUTTON}» — посмотреть чек, «{WRITE_BUTTON}» — написать покупателю.")
    return "\n".join(lines)

def history_keyboard(rows: list, final_buttons: bool = True) -> list:
    keyboard = []
    for row in rows[:20]:
        order_id = row.get("id", "")
        if not order_id:
            continue
        buttons = [btn(f"{PROOF_BUTTON} #{order_id}", f"proof:{order_id}")]
        if final_buttons:
            buttons.append(btn(f"✍️ #{order_id}", f"chat:{order_id}"))
        keyboard.append(buttons)
    return keyboard

def admin_welcome_keyboard() -> list:
    return [
        [btn(ORDERS_BUTTON, "orders")],
        [btn(HISTORY_BUTTON, "history"), btn(STATS_BUTTON, "stats")],
        [btn(LINK_BUTTON, "link")],
    ]

def stats_text(cfg, stats: dict, admins: list) -> str:
    return (
        "📊 <b>Статистика</b>\n\n"
        f"Всего заявок: <b>{stats['total']}</b>\n"
        f"🕓 В ожидании: {stats['pending']}\n"
        f"⏳ Ждут фото: {stats.get('awaiting_product', 0)}\n"
        f"✅ Выполнено: {stats['accepted']}\n"
        f"❌ Отклонено: {stats['rejected']}\n"
        f"🚫 Отменено покупателем: {stats.get('cancelled', 0)}\n\n"
        f"Операторы: {len(admins)}"
    )

def link_text(cfg) -> str:
    if cfg.bot_username:
        return (
            "🔗 <b>Ссылка для покупателей</b>\n\n"
            f"https://t.me/{esc(cfg.bot_username)}\n\n"
            "Отправь её покупателю — он откроет бота и оформит заявку."
        )
    return "BOT_USERNAME не задан в .env — ссылку показать не могу."

def unknown_command(cfg) -> str:
    return "Не знаю такую команду. Список команд: /start"
