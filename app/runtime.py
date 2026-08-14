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
from dataclasses import dataclass, field
from datetime import datetime

from app.agents.context import Decision, build_context
from app.agents.replier import (
    draft_reply,
    to_admin_card,
    with_disclosure,
)
from app.agents.writer import POST_KINDS, write_post
from app.config import Settings
from app.media.library import pick as pick_asset
from app.spine import approval
from app.spine.scheduler import (
    Slot, due_slots, next_slot, now_tashkent, slot_from_key,
    slots_needing_approval,
)
from app.spine.states import Content, State, publishable
from app.spine.store import Store
from app.telegram.api import BotAPI, TelegramError
from app.telegram.classifier import Kind, classify
from app.telegram.publisher import find_thread_root

log = logging.getLogger("runtime")

REACTION = "🔥"

#: On a cold start Telegram hands over every queued update, some hours old.
#: The first deployment answered a whole stale thread in 30 seconds because of
#: this. Anything older than the window is read for context and never replied to.
MAX_REPLY_AGE_S = 15 * 60

#: However large the backlog, do not post more than this many replies into one
#: thread in a single pass. A cap turns a bad run into two odd replies rather
#: than eight.
MAX_REPLIES_PER_THREAD_PER_RUN = 2

#: States where the slot still owes a draft. Everything else is either waiting on
#: the approver or already settled. Stated positively on purpose: the old check
#: was "is not REJECTED", which quietly excluded DRAFTING and NEEDS_REVISION and
#: turned the revise button into a way to delete a slot.
NEEDS_DRAFTING = {State.DRAFTING, State.NEEDS_REVISION, State.REJECTED}

#: How many times a slot may be redrafted after rejection before it is left
#: to the backup pool. Bounded so a genuinely impossible brief cannot burn
#: tokens every fifteen minutes forever.
MAX_REDRAFTS = 3

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
    _replied_this_run: dict[int, int] = field(default_factory=dict)

    # --- listening ----------------------------------------------------------

    def drain_updates(self) -> int:
        offset = self.store.get_runtime("update_offset")
        if offset is None:
            # Cold start. Take only the newest update to establish an offset and
            # discard the queued backlog: those messages are already answered, by
            # the founders or by each other, and replying now is necroposting.
            latest = self.api.get_updates(offset=-1, timeout=0)
            if latest:
                self.store.set_runtime("update_offset", str(latest[-1]["update_id"] + 1))
                log.warning("cold start: skipped %s queued update(s)", len(latest))
            else:
                self.store.set_runtime("update_offset", "0")
            return 0

        updates = self.api.get_updates(
            offset=int(offset), timeout=25,
            allowed_updates=["message", "channel_post", "callback_query"],
        )
        self._replied_this_run.clear()
        batch = [u["message"] for u in updates if "message" in u]
        for update in updates:
            update["_batch"] = batch
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
        if not message:
            return

        chat_id = (message.get("chat") or {}).get("id")
        if chat_id == self.settings.admin_chat_id:
            self.handle_admin_command(message)
            return

        if chat_id != self.settings.discussion_group_id:
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

        self.handle_comment(message, update.get("_batch") or [])

    #: What the founders can ask the bot in the admin chat. Deliberately tiny:
    #: the batch review belongs in the Mini App, and this is the safety valve for
    #: when a card did not arrive.
    COMMANDS = ("/pending", "/kutilmoqda", "/holat", "/status")

    def handle_admin_command(self, message: dict) -> None:
        text = (message.get("text") or "").strip().lower().split("@")[0]
        user_id = (message.get("from") or {}).get("id")
        if self.settings.approver_ids and user_id not in self.settings.approver_ids:
            return
        if text in ("/pending", "/kutilmoqda"):
            log.info("admin asked for the approval queue")
            self.send_pending_digest()
        elif text in ("/holat", "/status"):
            waiting = len(self.pending_approvals())
            self._alert(
                f"🗓 Keyingi slot: <b>{next_slot().key}</b>\n"
                f"⏳ Tasdiqlashni kutmoqda: <b>{waiting}</b>\n"
                f"🛟 Zaxira postlar: <b>{self.store.backup_count()}</b>"
            )

    def handle_comment(self, message: dict, batch: list[dict] | None = None) -> None:
        roots = self.store.known_roots()
        thread_id = message.get("message_thread_id")
        if thread_id not in roots:
            replied = message.get("reply_to_message") or {}
            thread_id = replied.get("message_id") if replied.get("message_id") in roots else None
        if thread_id is None:
            return  # group chatter outside any comment thread

        # Old messages are recorded for context but never answered.
        age = time.time() - (message.get("date") or time.time())
        if age > MAX_REPLY_AGE_S:
            log.info("message %s is %.0fs old; recording without replying",
                     message["message_id"], age)
            self._record_only(message, thread_id, "skip_too_old")
            return

        if self._replied_this_run.get(thread_id, 0) >= MAX_REPLIES_PER_THREAD_PER_RUN:
            log.info("thread %s hit the per-run reply cap; skipping %s",
                     thread_id, message["message_id"])
            self._record_only(message, thread_id, "skip_rate_limited")
            return

        # Siblings come from this batch as well as from storage. On a fresh
        # database storage is empty, which is how the already-answered rule was
        # bypassed on the first live run.
        siblings = self._thread_messages(thread_id, message, batch or [])
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
            message["message_id"], decision="reply", reply_message_id=sent_id,
            reply_text=text, **record
        )
        self._replied_this_run[thread_id] = self._replied_this_run.get(thread_id, 0) + 1
        log.info("replied to %s in thread %s", message["message_id"], thread_id)

    def _record_only(self, message: dict, thread_id: int, decision: str) -> None:
        frm = message.get("from") or {}
        self.store.record_comment(
            message["message_id"], thread_id, author_id=frm.get("id"),
            author_name=frm.get("first_name", "?"),
            text=(message.get("text") or message.get("caption") or ""),
            script="", decision=decision,
        )

    def _thread_messages(self, thread_id: int, message: dict,
                         batch: list[dict] | None = None) -> list[dict]:
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
        from_batch = [
            m for m in (batch or [])
            if (m.get("chat") or {}).get("id") == self.settings.discussion_group_id
            and m.get("message_id") not in {r["message_id"] for r in rows}
            and m.get("message_id") != message["message_id"]
        ]
        return [root, *rebuilt, *from_batch, message]

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

    def report_state(self) -> None:
        """Log everything needed to explain a missed slot, at every startup.

        A slot went unpublished and the container had been replaced, so the only
        record of why was gone. Scheduler state is cheap to print and impossible
        to reconstruct afterwards.
        """
        last = self.store.last_seen
        log.info("state: last_seen=%s", last.isoformat() if last else "NONE (first boot — publishes nothing)")
        log.info("state: now=%s next_slot=%s", now_tashkent().isoformat(timespec="seconds"),
                 next_slot().key)
        # times_used is the forensic record. A slot that fell back to the pool
        # leaves a used row behind; a slot that never reached publish_slot at all
        # leaves the pool pristine. Nothing else distinguishes those two.
        for row in self.store._conn.execute(
            "SELECT id, times_used, last_used_at, substr(text,1,40) AS head "
            "FROM backup_pool ORDER BY id"
        ):
            log.info("state: backup #%s used=%s at=%s | %s",
                     row["id"], row["times_used"], row["last_used_at"] or "never", row["head"])

        for row in self.store._conn.execute(
            "SELECT slot_key, kind, state FROM content ORDER BY slot_key DESC LIMIT 8"
        ):
            log.info("state: content %s (%s) -> %s", row["slot_key"], row["kind"], row["state"])

    def publish_due(self) -> None:
        last = self.store.last_seen
        publish, too_late = due_slots(last)
        if publish or too_late:
            log.info("due: last_seen=%s publish=%s too_late=%s",
                     last.isoformat(timespec="seconds") if last else None,
                     [s.key for s in publish], [s.key for s in too_late])
        for slot in too_late:
            log.warning("slot %s missed its window; skipped", slot.key)
            content = self.store.get_content(slot.key)
            if content and not content.is_terminal:
                content.expire("missed its publishing window")
                self.store.save_content(content)

        for slot in publish:
            try:
                self.publish_slot(slot)
            except Exception as exc:
                # One slot's failure must not take the next one down with it, and
                # must not stall last_seen — a stalled last_seen re-attempts the
                # same broken slot every tick until the lateness cap, silently.
                log.exception("slot %s failed to publish", slot.key)
                self._alert(f"❌ <b>{slot.key}</b> chiqmadi\n\n<code>{exc}</code>")
        self.store.last_seen = now_tashkent()

    def publish_slot(self, slot: Slot) -> None:
        content = self.store.get_content(slot.key)

        if content and publishable(content):
            text = content.text
        else:
            if content and not content.is_terminal:
                content.expire()
                self.store.save_content(content)
            log.warning("slot %s has no approved content (%s); falling back to backup",
                        slot.key, content.state.value if content else "nothing drafted")
            picked = self.store.take_backup()
            if not picked:
                log.error("slot %s unapproved and backup pool is EMPTY — channel silent", slot.key)
                self._alert(f"🔇 <b>{slot.key}</b> — kanal jim qoldi.\n"
                            f"Zaxira postlar tugagan.")
                return
            log.warning("slot %s unapproved; publishing backup %s", slot.key, picked[0])
            text = picked[1]

        # Founder direction: every post ships with a visual. Text alone does not
        # earn a read — people want to see what the thing can do first. If no
        # asset genuinely matches, the post still goes out as text; a mismatched
        # video is worse than none.
        used = {row[0] for row in self.store._conn.execute(
            "SELECT value FROM runtime WHERE key LIKE 'asset_used:%'")}
        asset = pick_asset(kind_for(slot), used=used)

        if self.dry_run:
            log.info("[dry-run] would publish slot %s with %s", slot.key,
                     asset.id if asset else "no media")
            return

        if asset:
            try:
                sender = self.api.send_video if asset.is_video else self.api.send_photo
                posted = sender(self.settings.channel_id, asset.url, caption=text)
                self.store.set_runtime(f"asset_used:{asset.id}", asset.id)
                log.info("published %s with asset %s", slot.key, asset.id)
            except TelegramError as exc:
                # An expired CDN URL must not cost the slot. Fall back to text.
                log.warning("media send failed (%s); publishing text only", exc)
                posted = self.api.send_message(self.settings.channel_id, text)
        else:
            posted = self.api.send_message(self.settings.channel_id, text)
        if content and publishable(content):
            content.publish(posted["message_id"])
            self.store.save_content(content)
        self.store.record_thread(posted["message_id"], 0, slot_key=slot.key)
        log.info("published %s as message %s", slot.key, posted["message_id"])

    # --- preparing ----------------------------------------------------------

    def prepare_upcoming(self) -> None:
        """Draft and send for approval anything inside the horizon."""
        upcoming = slots_needing_approval()
        log.info("preparing: %s slot(s) inside the horizon", len(upcoming))
        for slot in upcoming:
            existing = self.store.get_content(slot.key)
            if existing and existing.state not in NEEDS_DRAFTING:
                log.debug("%s already %s", slot.key, existing.state.value)
                if (existing.state is State.PENDING_APPROVAL
                        and not self.store.get_runtime(f"card_sent:{slot.key}")):
                    log.warning("%s is pending approval but its card was never "
                                "delivered; resending", slot.key)
                    self._send_for_approval(existing, slot)
                continue
            if existing:
                # A draft that still owes work used to block its slot forever:
                # the check was "does content exist" rather than "is it still
                # viable". Pressing ✏️ Qayta yozish was the worst case — it moves
                # content to DRAFTING, which is not REJECTED, so asking for a
                # rewrite silently killed the slot instead of producing one.
                attempts = int(self.store.get_runtime(f"redraft:{slot.key}") or 0)
                if attempts >= MAX_REDRAFTS:
                    log.warning("%s still %s after %s attempts; leaving it to the "
                                "backup pool", slot.key, existing.state.value, attempts)
                    continue
                self.store.set_runtime(f"redraft:{slot.key}", str(attempts + 1))
                log.info("%s is %s; redrafting (attempt %s)",
                         slot.key, existing.state.value, attempts + 1)

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
            log.info("approval card sent for %s (%s)", slot.key, kind)

    def _send_for_approval(self, content: Content, slot: Slot) -> bool:
        """Deliver the card, and record delivery only once it has happened.

        The state used to be committed before the send. If the send then failed,
        the slot sat in PENDING_APPROVAL forever — the guard in prepare_upcoming
        skips anything not REJECTED, so the card was never retried and the
        founders simply never saw that slot again.
        """
        if self.dry_run or not self.settings.admin_chat_id:
            log.info("[dry-run] approval card for %s", slot.key)
            return False
        try:
            self.api.send_message(
                self.settings.admin_chat_id,
                approval.card(content, slot),
                parse_mode="HTML",
                reply_markup=approval.keyboard(slot.key),
            )
        except TelegramError:
            # Left unrecorded on purpose: the next pass retries it.
            log.exception("approval card for %s did not send; will retry", slot.key)
            return False
        self.store.set_runtime(f"card_sent:{slot.key}", now_tashkent().isoformat())
        return True

    def pending_approvals(self) -> list[tuple[Content, Slot]]:
        return [
            (c, slot_from_key(c.slot_key))
            for c in self.store.content_in_state(State.PENDING_APPROVAL)
        ]

    def send_pending_digest(self) -> int:
        """Re-send every card still awaiting a decision.

        Cards arrive as slots cross the drafting horizon, which in Tashkent time
        can be the middle of the night in Sweden. One missed notification used to
        mean that post was gone. This makes the queue pullable on demand.
        """
        waiting = sorted(self.pending_approvals(), key=lambda pair: pair[1].at)
        if not waiting:
            self._alert("✅ Hammasi koʻrildi — kutayotgan post yoʻq.")
            return 0
        self._alert(f"🗂 <b>{len(waiting)} ta post</b> tasdiqlashni kutmoqda:")
        for content, slot in waiting:
            self._send_for_approval(content, slot)
        return len(waiting)

    def _alert(self, html: str) -> None:
        """Tell the founders something went wrong, and never raise doing it.

        A missed slot used to be entirely invisible: the channel simply stayed
        quiet and nobody knew until someone thought to look. Silence is the one
        failure mode this bot must never keep to itself.
        """
        if self.dry_run or not self.settings.admin_chat_id:
            return
        try:
            self.api.send_message(self.settings.admin_chat_id, html, parse_mode="HTML")
        except Exception:
            log.exception("could not deliver alert to the admin chat")

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
        self.report_state()
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
