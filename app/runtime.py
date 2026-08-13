"""The long-running process. Everything else is a library; this is the bot.

One loop, three jobs:

* **listen** — route Telegram updates: catch auto-forwards to learn thread roots,
  answer comments, apply approval button presses.
* **publish** — at 10:00 and 21:00 Tashkent, ship the approved post for that slot,
  or a backup post if none was approved.
* **prepare** — draft tomorrow's posts and send them for approval a day ahead.

The ordering inside a tick matters. Updates are drained before publishing, so a
slot's approval that arrived seconds ago is seen before the slot fires.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from app.agents.context import Decision, build_context
from app.agents.replier import (
    draft_reply,
    to_admin_card,
    with_disclosure,
)
from app.agents.writer import POST_KINDS, write_post
from app.config import Settings
from app.spine import approval
from app.spine.scheduler import Slot, due_slots, now_tashkent, slots_needing_approval
from app.spine.states import Content, State, publishable
from app.spine.store import Store
from app.telegram.api import BotAPI, TelegramError
from app.telegram.classifier import Kind, classify
from app.telegram.publisher import find_thread_root

log = logging.getLogger("runtime")

REACTION = "🔥"

#: The weekly grid, by weekday and slot hour. Monday is 0.
WEEKLY_PLAN: dict[tuple[int, int], str] = {
    (0, 10): "technique",      (0, 21): "commercial_craft",
    (1, 10): "news",           (1, 21): "why_content",
    (2, 10): "technique",      (2, 21): "poll",
    (3, 10): "commercial_craft", (3, 21): "behind_scenes",
    (4, 10): "news",           (4, 21): "challenge",
    (5, 10): "mission",        (5, 21): "technique",
    (6, 10): "recognition",    (6, 21): "recap",
}


def kind_for(slot: Slot) -> str:
    return WEEKLY_PLAN.get((slot.at.weekday(), slot.at.hour), "technique")


@dataclass
class Runtime:
    settings: Settings
    store: Store
    api: BotAPI
    bot_id: int
    dry_run: bool = False

    # --- listening ----------------------------------------------------------

    def drain_updates(self) -> int:
        offset = self.store.get_runtime("update_offset")
        updates = self.api.get_updates(
            offset=int(offset) if offset else None,
            timeout=25,
            allowed_updates=["message", "channel_post", "callback_query"],
        )
        for update in updates:
            try:
                self.handle_update(update)
            except Exception:
                # One malformed update must never stop the loop; the offset still
                # advances so it is not retried forever.
                log.exception("update %s failed", update.get("update_id"))
            self.store.set_runtime("update_offset", str(update["update_id"] + 1))
        return len(updates)

    def handle_update(self, update: dict) -> None:
        if "callback_query" in update:
            self.handle_callback(update["callback_query"])
            return

        message = update.get("message")
        if not message or (message.get("chat") or {}).get("id") != self.settings.discussion_group_id:
            return

        result = classify(message, bot_id=self.bot_id, channel_id=self.settings.channel_id)

        if result.kind is Kind.THREAD_ROOT:
            # The only moment this mapping exists. Persist before anything else.
            if result.origin_message_id:
                self.store.record_thread(result.origin_message_id, message["message_id"])
                log.info("thread root %s -> post %s", message["message_id"], result.origin_message_id)
            return

        if result.kind is not Kind.HUMAN or self.store.seen_comment(message["message_id"]):
            return

        self.handle_comment(message)

    def handle_comment(self, message: dict) -> None:
        roots = self.store.known_roots()
        thread_id = message.get("message_thread_id")
        if thread_id not in roots:
            replied = message.get("reply_to_message") or {}
            thread_id = replied.get("message_id") if replied.get("message_id") in roots else None
        if thread_id is None:
            return  # group chatter outside any comment thread

        siblings = self._thread_messages(thread_id, message)
        ctx = build_context(
            message["message_id"], siblings,
            bot_id=self.bot_id, channel_id=self.settings.channel_id,
            thread_root_id=thread_id,
        )

        record = dict(
            group_root_id=thread_id,
            author_id=(message.get("from") or {}).get("id"),
            author_name=(message.get("from") or {}).get("first_name", "?"),
            text=ctx.target.text,
            script=ctx.script.value,
        )

        if ctx.decision is Decision.REACT:
            if not self.dry_run:
                try:
                    self.api.set_message_reaction(
                        self.settings.discussion_group_id, message["message_id"], REACTION
                    )
                except TelegramError as exc:
                    log.warning("reaction failed: %s", exc)
            self.store.record_comment(message["message_id"], decision="react", **record)
            return

        if not ctx.should_reply:
            self.store.record_comment(message["message_id"], decision=ctx.decision.value, **record)
            return

        prior = self.store.replies_in_thread(thread_id)
        draft = draft_reply(
            ctx, api_key=self.settings.anthropic_api_key or "", previous_drafts=prior
        )

        if not draft.is_reply:
            self._escalate(ctx, draft)
            self.store.record_comment(message["message_id"], decision="escalate", **record)
            return

        text = with_disclosure(draft.draft, first_in_thread=not prior)
        sent_id = None
        if not self.dry_run:
            sent = self.api.send_message(
                self.settings.discussion_group_id, text,
                reply_to_message_id=message["message_id"],
            )
            sent_id = sent["message_id"]
        self.store.record_comment(
            message["message_id"], decision="reply", reply_message_id=sent_id, **record
        )
        log.info("replied to %s in thread %s", message["message_id"], thread_id)

    def _thread_messages(self, thread_id: int, message: dict) -> list[dict]:
        """Reconstruct enough thread context for a reply decision.

        Only the current message is guaranteed present; the rest comes from what
        we recorded. Good enough for the already-answered check, which is the
        rule that actually depends on siblings.
        """
        rows = self.store._conn.execute(
            "SELECT message_id, author_id, author_name, text FROM comments "
            "WHERE group_root_id=? ORDER BY message_id",
            (thread_id,),
        ).fetchall()
        rebuilt = [
            {
                "message_id": r["message_id"],
                "chat": {"id": self.settings.discussion_group_id, "type": "supergroup"},
                "from": {"id": r["author_id"], "is_bot": False, "first_name": r["author_name"]},
                "text": r["text"] or "",
                "message_thread_id": thread_id,
            }
            for r in rows if r["message_id"] != message["message_id"]
        ]
        root = {
            "message_id": thread_id,
            "chat": {"id": self.settings.discussion_group_id, "type": "supergroup"},
            "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
            "is_automatic_forward": True,
            "forward_origin": {"type": "channel", "chat": {"id": self.settings.channel_id}},
            "text": "",
        }
        return [root, *rebuilt, message]

    def _escalate(self, ctx, draft) -> None:
        if self.dry_run or not self.settings.admin_chat_id:
            log.info("escalation (not sent): %s", draft.needs_from_founders)
            return
        self.api.send_message(
            self.settings.admin_chat_id, to_admin_card(ctx, draft), parse_mode="HTML"
        )

    def handle_callback(self, query: dict) -> None:
        action, slot_key = approval.parse_callback(query.get("data", ""))
        content = self.store.get_content(slot_key)
        outcome = approval.handle_callback(
            action, content,
            user_id=(query.get("from") or {}).get("id", 0),
            approver_ids=self.settings.approver_ids,
            at=now_tashkent(),
        )
        self.api.answer_callback_query(query["id"], outcome.toast)
        if outcome.handled and content:
            self.store.save_content(content)
            msg = query.get("message") or {}
            if msg:
                try:
                    self.api.edit_message_text(
                        msg["chat"]["id"], msg["message_id"],
                        f"{outcome.verdict_line}\n\n{content.text}", parse_mode="HTML",
                    )
                except TelegramError as exc:
                    log.warning("card edit failed: %s", exc)

    # --- publishing ---------------------------------------------------------

    def publish_due(self) -> None:
        publish, too_late = due_slots(self.store.last_seen)
        for slot in too_late:
            log.warning("slot %s missed its window; skipped", slot.key)
            content = self.store.get_content(slot.key)
            if content and not content.is_terminal:
                content.expire("missed its publishing window")
                self.store.save_content(content)

        for slot in publish:
            self.publish_slot(slot)
        self.store.last_seen = now_tashkent()

    def publish_slot(self, slot: Slot) -> None:
        content = self.store.get_content(slot.key)

        if content and publishable(content):
            text = content.text
        else:
            if content and not content.is_terminal:
                content.expire()
                self.store.save_content(content)
            picked = self.store.take_backup()
            if not picked:
                log.error("slot %s unapproved and backup pool is EMPTY — channel silent", slot.key)
                return
            log.warning("slot %s unapproved; publishing backup %s", slot.key, picked[0])
            text = picked[1]

        if self.dry_run:
            log.info("[dry-run] would publish to slot %s", slot.key)
            return

        posted = self.api.send_message(self.settings.channel_id, text)
        if content and publishable(content):
            content.publish(posted["message_id"])
            self.store.save_content(content)
        self.store.record_thread(posted["message_id"], 0, slot_key=slot.key)
        log.info("published %s as message %s", slot.key, posted["message_id"])

    # --- preparing ----------------------------------------------------------

    def prepare_upcoming(self) -> None:
        """Draft and send for approval anything inside the horizon."""
        for slot in slots_needing_approval():
            if self.store.get_content(slot.key):
                continue
            kind = kind_for(slot)
            log.info("drafting %s for %s", kind, slot.key)
            post = write_post(
                kind,
                api_key=self.settings.anthropic_api_key or "",
                brief=POST_KINDS.get(kind),
                recent=[c.text for c in self.store.content_in_state(State.PUBLISHED)][-5:],
            )
            content = Content(slot_key=slot.key, kind=kind, text=post.text)

            if not post.ok:
                # Never silently ship what the critic would not pass.
                log.warning("%s not publishable: %s", slot.key, post.problem)
                self._send_problem(slot, post)
                content.reject(post.problem)
                self.store.save_content(content)
                continue

            content.submit_for_approval()
            self.store.save_content(content)
            self._send_for_approval(content, slot)

    def _send_for_approval(self, content: Content, slot: Slot) -> None:
        if self.dry_run or not self.settings.admin_chat_id:
            log.info("[dry-run] approval card for %s", slot.key)
            return
        self.api.send_message(
            self.settings.admin_chat_id,
            approval.card(content, slot),
            parse_mode="HTML",
            reply_markup=approval.keyboard(slot.key),
        )

    def _send_problem(self, slot: Slot, post) -> None:
        if self.dry_run or not self.settings.admin_chat_id:
            return
        self.api.send_message(
            self.settings.admin_chat_id,
            f"⚠️ <b>{slot.key}</b> ({post.kind}) tayyor emas\n\n<code>{post.problem}</code>",
            parse_mode="HTML",
        )

    # --- the loop -----------------------------------------------------------

    def tick(self) -> None:
        self.drain_updates()   # approvals arriving now must be seen before publishing
        self.publish_due()

    def run(self, *, prepare_every: int = 900) -> None:
        last_prepare = 0.0
        log.info("runtime started; next slot handling on tick")
        while True:
            try:
                self.tick()
                if time.monotonic() - last_prepare > prepare_every:
                    self.prepare_upcoming()
                    last_prepare = time.monotonic()
            except TelegramError as exc:
                wait = exc.retry_after or 5
                log.warning("telegram error: %s (waiting %ss)", exc, wait)
                time.sleep(wait)
            except Exception:
                log.exception("tick failed")
                time.sleep(10)


def build(settings: Settings | None = None, *, db_path: str = "data/bot.db",
          dry_run: bool = False) -> Runtime:
    settings = settings or Settings.load()
    api = BotAPI(settings.bot_token)
    me = api.get_me()
    return Runtime(
        settings=settings, store=Store(db_path), api=api,
        bot_id=me["id"], dry_run=dry_run,
    )
