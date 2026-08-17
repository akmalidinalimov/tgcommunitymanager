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

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

from app.agents.context import Decision, build_context
from app.agents.research import Finding, is_price_question, lookup_price
from app.agents.replier import (
    draft_reply,
    to_admin_card,
    with_disclosure,
)
from app.agents.writer import POST_KINDS, write_post
from app.config import Settings
from html import escape
from app.media import cards
from app.media.cards import fetch_image
from app.media.library import get as asset_by_id
from app.media.library import pick as pick_asset
from app.spine import approval
from app.spine.planned import load as load_planned
from app.spine.scheduler import (
    Slot, due_slots, next_slot, now_tashkent, slot_from_key,
    slots_needing_approval,
)
from app.spine.states import Content, State, publishable
from app.spine.store import Store
from app.telegram.api import BotAPI, TelegramError
from app.telegram.classifier import Kind, classify
from app.telegram.publisher import find_thread_root
from app.text.lint import CAPTION_CAP, blockers, lint
from app.text.orthography import normalize_apostrophes

log = logging.getLogger("runtime")

REACTION = "🔥"

#: Recorded on content whose visual is a card drawn here rather than a library
#: asset. Not a path: the render is deterministic and is redrawn at send time.
CARD = "card"

#: Marks every message that needs a founder to decide something, so an
#: attention-needed message is never mistaken for routine bot chatter.
NEEDS_YOU = "🔴 <b>SIZDAN JAVOB KERAK</b>"

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


def _cache_key(question: str) -> str:
    """Stable key for a researched question, so the same one is not paid for twice."""
    return hashlib.sha256(question.strip().lower().encode()).hexdigest()[:16]


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
                self.seed_thread(result.origin_message_id, message["message_id"])
            return

        if result.kind is not Kind.HUMAN or self.store.seen_comment(message["message_id"]):
            return

        self.handle_comment(message, update.get("_batch") or [])

    #: What the founders can ask the bot in the admin chat. Deliberately tiny:
    #: the batch review belongs in the Mini App, and this is the safety valve for
    #: when a card did not arrive.
    COMMANDS = ("/pending", "/kutilmoqda", "/holat", "/status")

    def handle_admin_command(self, message: dict) -> None:
        raw = (message.get("text") or "").strip()
        text = raw.lower().split("@")[0]
        user_id = (message.get("from") or {}).get("id")
        if self.settings.approver_ids and user_id not in self.settings.approver_ids:
            return

        # Replying to a card does something with that card. Checked before the
        # command table so an answer that happens to start with a slash is still
        # an answer.
        replied_to = (message.get("reply_to_message") or {}).get("message_id")
        if replied_to and raw:
            if self.relay_founder_answer(replied_to, raw):
                return
            if self.apply_inline_edit(replied_to, raw):
                return

        if text in ("/pending", "/kutilmoqda"):
            log.info("admin asked for the approval queue")
            self.send_pending_digest()
        elif text in ("/holat", "/status"):
            waiting = len(self.pending_approvals())
            self._alert(
                f"🗓 Keyingi slot: <b>{next_slot().key}</b>\n"
                f"⏳ Tasdiqlashni kutmoqda: <b>{waiting}</b>\n"
                f"❓ Javobsiz savollar: <b>{self.unanswered_questions()}</b>\n"
                f"🛟 Zaxira postlar: <b>{self.store.backup_count()}</b>"
            )

    def apply_inline_edit(self, card_message_id: int, replacement: str) -> bool:
        """Replace a pending post's text with what the approver just typed.

        ✏️ Qayta yozish costs an LLM round-trip and returns something Shahlo did
        not write. When one line is wrong, typing the line is faster and exact.
        The text still goes through the same lint the Writer's output does — a
        hand-typed post can break the caption cap or the banned constructions
        just as easily, and it publishes to 3,326 people either way.
        """
        slot_key = self.store.get_runtime(f"card:{card_message_id}")
        if not slot_key:
            return False

        content = self.store.get_content(slot_key)
        if not content or content.state is not State.PENDING_APPROVAL:
            self._alert(f"⚠️ <b>{escape(slot_key)}</b> tahrirlab boʻlmaydi "
                        f"({content.state.value if content else 'topilmadi'}).")
            return True

        text = normalize_apostrophes(replacement)
        problems = blockers(lint(text))
        if problems:
            self._alert(f"⚠️ Tahrir qabul qilinmadi:\n\n<code>"
                        f"{escape('; '.join(str(p) for p in problems))}</code>")
            return True

        content.set_text(text)
        self.store.save_content(content)
        slot = slot_from_key(slot_key)
        log.info("%s edited by hand in the admin chat", slot_key)
        self._alert(f"✏️ <b>{escape(slot_key)}</b> yangilandi. Tasdiqlang:")
        self._send_for_approval(content, slot)
        return True

    def seed_thread(self, channel_message_id: int, group_root_id: int) -> bool:
        """Post the bot's own first comment into a freshly opened thread.

        The auto-forward is the only moment the post-to-thread mapping exists, so
        this is also the only moment the seed can be placed. It must be a reply to
        the forwarded message — `message_thread_id` on send is silently ignored
        and the comment lands in the group's main feed in front of everyone.

        This is the north-star mechanism. The discussion group has three members
        against the channel's 3,326 because the comment section has effectively
        never been used, and an empty section is the hardest one to be first in.
        """
        slot_key = self.store.slot_for_post(channel_message_id)
        content = self.store.get_content(slot_key) if slot_key else None
        if not content or not content.seed_comment.strip():
            return False
        if self.dry_run:
            log.info("[dry-run] would seed thread %s", group_root_id)
            return True

        try:
            seeded = self.api.send_message(
                self.settings.discussion_group_id,
                with_disclosure(content.seed_comment, first_in_thread=True),
                reply_to_message_id=group_root_id,
            )
        except TelegramError as exc:
            log.warning("could not seed thread %s: %s", group_root_id, exc)
            return False

        self.store.record_thread(channel_message_id, group_root_id,
                                 slot_key=slot_key, seeded_message_id=seeded["message_id"])
        log.info("seeded thread %s for %s", group_root_id, slot_key)
        return True

    def relay_founder_answer(self, card_message_id: int, answer: str) -> bool:
        """Deliver a founder's typed answer into the member's comment thread.

        The escalation used to be one-way: the bot asked, the founders answered
        in the admin chat, and the answer stopped there because nothing was
        listening. The member — who asked in public and waited — got nothing.

        Sent verbatim. It is the founders' own sentence, so it is not rewritten,
        not shortened, and not given the AI-disclosure line: that line exists to
        stop a reader mistaking machine text for human text, and this is human
        text. It is recorded with its own decision so the disclosure gate still
        counts the bot's own replies correctly.
        """
        stored = self.store.get_runtime(f"esc:{card_message_id}")
        if not stored:
            return False

        link = json.loads(stored)
        member_message_id = link["member_message_id"]
        if self.dry_run:
            log.info("[dry-run] would relay founder answer to %s", member_message_id)
            return True

        try:
            sent = self.api.send_message(
                self.settings.discussion_group_id,
                normalize_apostrophes(answer),
                reply_to_message_id=member_message_id,
            )
        except TelegramError as exc:
            log.warning("could not relay the founder answer: %s", exc)
            self._alert(f"⚠️ Javobingizni yetkaza olmadim: <code>{escape(str(exc))}</code>")
            return True

        self.store.record_comment(
            member_message_id, link["thread_id"],
            author_id=None, author_name=link.get("author", "?"),
            text="", script="", decision="founder_reply",
            reply_message_id=sent["message_id"], reply_text=answer,
        )
        self.store.set_runtime(f"esc:{card_message_id}", "")
        log.info("relayed a founder answer to member message %s", member_message_id)
        self._alert(f"✅ Javobingiz <b>{escape(link.get('author', '?'))}</b> ga yuborildi.")
        return True

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

        finding = None
        if not draft.is_reply:
            # The grounding gate refused. If the missing fact is a price, go and
            # look it up rather than making the member wait on a founder for
            # something the vendor publishes openly.
            draft, finding = self._research_then_redraft(ctx, draft, prior)

        if not draft.is_reply:
            self._escalate(ctx, draft, finding)
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

    def _research_then_redraft(self, ctx, draft, prior: list[str]):
        """Try to answer an escalated price question from the open web.

        Returns (draft, finding). The draft is upgraded to a reply only when the
        finding clears every gate in `research`: a specific price, from the
        vendor's own page, with no conflicting sources and high confidence.
        Anything less goes to the founders WITH the evidence, so raising it is
        useful rather than a shrug.
        """
        question = draft.needs_from_founders or ctx.target.text
        if not is_price_question(ctx.target.text):
            return draft, None

        cached = self.store.get_runtime(f"price:{_cache_key(question)}")
        if cached:
            log.info("price question already researched; not searching again")
            return draft, Finding(**json.loads(cached))

        log.info("price question escalated; researching: %.80s", question)
        finding = lookup_price(question, api_key=self.settings.anthropic_api_key or "")
        if finding.searched:
            self.store.set_runtime(f"price:{_cache_key(question)}",
                                   json.dumps(asdict(finding), ensure_ascii=False))

        if not finding.quotable:
            log.info("finding is not quotable (%s); leaving it to the founders",
                     ", ".join(finding.blockers))
            return draft, finding

        upgraded = draft_reply(
            ctx, api_key=self.settings.anthropic_api_key or "",
            previous_drafts=prior, extra_facts=[finding.as_fact()],
        )
        log.info("redrafted with researched price -> %s", upgraded.action)
        return upgraded, finding

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

    def _escalate(self, ctx, draft, finding=None) -> None:
        if self.dry_run or not self.settings.admin_chat_id:
            log.info("escalation (not sent): %s", draft.needs_from_founders)
            return

        card = (f"{NEEDS_YOU}\n\n{to_admin_card(ctx, draft)}"
                f"\n\n<i>↩️ Shu xabarga javob yozing — men uni aʼzoga yetkazaman.</i>")
        if finding is not None and finding.searched:
            # Raising a question with the legwork already done is the difference
            # between "someone asked about pricing" and "here is what the web
            # says, here is why I would not publish it, here is the decision".
            why = ", ".join(finding.blockers) or "—"
            card += (
                f"\n\n🔎 <b>Men qidirib koʻrdim</b>\n"
                f"<i>Nega eʼlon qilmadim: {escape(why)}</i>\n\n"
                f"{escape(finding.summary_for_founders)}"
            )
            if finding.source_url:
                card += f"\n\n{escape(finding.source_url)}"
        sent = self.api.send_message(self.settings.admin_chat_id, card, parse_mode="HTML")

        # Remember which member this card is about, so replying to it in the
        # admin chat delivers the answer into the right comment thread. Without
        # this the founders' answers went nowhere — they were typed into a DM the
        # bot was not listening to.
        self.store.set_runtime(f"esc:{sent['message_id']}", json.dumps({
            "member_message_id": ctx.target.message_id,
            "thread_id": getattr(ctx, "thread_root_id", None) or 0,
            "author": ctx.target.author,
        }))

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

        # A button press decides what reaches 3,326 people and used to leave no
        # trace anywhere. Content state appears only in the boot dump, so the
        # only way to answer "did that get approved" was to restart a live bot.
        who = (query.get("from") or {}).get("id", 0)
        if outcome.handled and content:
            log.info("approval: %s pressed %r on %s -> %s",
                     who, action, slot_key, content.state.value)
        else:
            log.info("approval refused: %s pressed %r on %s -> %s",
                     who, action, slot_key, outcome.toast)

        if outcome.handled and content:
            self.store.save_content(content)
            msg = query.get("message") or {}
            if msg:
                # A card carrying a visual is a photo with a caption, and
                # editMessageText refuses one — "there is no text in the message
                # to edit" — so approving it left the card looking undecided.
                body = f"{outcome.verdict_line}\n\n{escape(content.text)}"
                edit = (self.api.edit_message_caption
                        if msg.get("photo") or msg.get("video")
                        else self.api.edit_message_text)
                try:
                    edit(msg["chat"]["id"], msg["message_id"], body, parse_mode="HTML")
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
        #
        # Approved content publishes the visual it was approved WITH. Picking one
        # here would mean the post that shipped is not the post anyone said yes
        # to. Only a backup, which nobody previewed, chooses at publish time.
        if content and publishable(content):
            visual = self.visual(content, content.kind, text)
        else:
            # A backup nobody previewed still obeys the rule that every post
            # carries a visual: a library asset if one fits, otherwise a card.
            asset = pick_asset(kind_for(slot), used=self._assets_used())
            visual = ("asset", asset) if asset else ("card", None)
            if visual[0] == "card":
                try:
                    visual = ("card", cards.render_post(kind_for(slot), text))
                except Exception:
                    log.exception("card render failed; publishing text only")
                    visual = (None, None)

        if self.dry_run:
            log.info("[dry-run] would publish slot %s with %s", slot.key,
                     asset.id if asset else "no media")
            return

        try:
            posted = self._deliver(self.settings.channel_id, visual, text)
            if visual[0] == "asset":
                self.store.set_runtime(f"asset_used:{visual[1].id}", visual[1].id)
            log.info("published %s with %s", slot.key, visual[0] or "no media")
        except TelegramError as exc:
            # An expired CDN URL must not cost the slot. Fall back to text.
            log.warning("media send failed (%s); publishing text only", exc)
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

            # A planned post replaces whatever the Writer produced for that slot.
            # Checked BEFORE the has-content guard: by the time a plan is written
            # the Writer has usually already drafted and sent a card, and without
            # this the plan would silently never apply. Approved content is left
            # alone — what a human said yes to is immutable.
            plan = load_planned().get(slot.key)
            if plan and existing and not existing.frozen and existing.text != plan.text:
                log.info("%s replaced by the planned post", slot.key)
                self.store.set_runtime(f"card_sent:{slot.key}", "")
                existing = None

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

            # A post the founders wrote themselves wins over the Writer. It has
            # already passed lint in planned.load(), so it goes straight to
            # approval rather than through the critic loop.
            planned = load_planned().get(slot.key)
            if planned:
                log.info("%s uses a planned post (%s)", slot.key, planned.kind)
                content = Content(slot_key=slot.key, kind=planned.kind,
                                  text=planned.text, seed_comment=planned.seed_comment)
                content.attach_media(planned.asset or CARD)
                content.submit_for_approval()
                self.store.save_content(content)
                if self._send_for_approval(content, slot):
                    log.info("approval card sent for %s (planned)", slot.key)
                else:
                    log.warning("planned card for %s did not send; will retry", slot.key)
                continue

            log.info("drafting %s for %s", kind, slot.key)
            post = write_post(
                kind,
                api_key=self.settings.anthropic_api_key or "",
                brief=POST_KINDS.get(kind),
                recent=[c.text for c in self.store.content_in_state(State.PUBLISHED)][-5:],
            )
            content = Content(slot_key=slot.key, kind=kind, text=post.text,
                              seed_comment=post.seed_comment)

            if not post.ok:
                # Never silently ship what the critic would not pass.
                log.warning("%s not publishable: %s", slot.key, post.problem)
                self._send_problem(slot, post)
                content.reject(post.problem)
                self.store.save_content(content)
                continue

            # Bind the visual now, not at publish time. Founder direction is that
            # every post ships with a visual, and an approver who only ever sees
            # the caption is approving half the post. Choosing the asset after
            # approval would also mean what shipped was not what was said yes to.
            asset = pick_asset(kind, used=self._assets_used())
            content.attach_media(asset.id if asset else CARD)
            if not asset:
                log.info("%s (%s) has no matching photograph; it gets a card",
                         slot.key, kind)

            content.submit_for_approval()
            self.store.save_content(content)
            if self._send_for_approval(content, slot):
                log.info("approval card sent for %s (%s) with %s", slot.key, kind,
                         asset.id if asset else "no media")
            else:
                log.warning("card for %s did not send; will retry", slot.key)

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
        body = approval.card(content, slot)
        buttons = approval.keyboard(slot.key)
        visual = self.visual(content, content.kind, content.text)
        try:
            if visual[0] and len(body) > CAPTION_CAP:
                # Too long to ride as a caption. Show the visual, then the text
                # with the buttons, rather than silently dropping either.
                self._deliver(self.settings.admin_chat_id, visual, "")
                sent = self.api.send_message(self.settings.admin_chat_id, body,
                                             parse_mode="HTML", reply_markup=buttons)
            else:
                # The card IS the post: the visual with the caption under it,
                # exactly as the channel will see it. A preview that differs from
                # production is worse than no preview.
                sent = self._deliver(self.settings.admin_chat_id, visual, body,
                                     parse_mode="HTML", reply_markup=buttons)
        except TelegramError:
            # Left unrecorded on purpose: the next pass retries it.
            log.exception("approval card for %s did not send; will retry", slot.key)
            return False
        self.store.set_runtime(f"card_sent:{slot.key}", now_tashkent().isoformat())
        if isinstance(sent, dict) and sent.get("message_id"):
            self.store.set_runtime(f"card:{sent['message_id']}", slot.key)
        return True

    def unanswered_questions(self) -> int:
        """Escalations nobody has replied to yet.

        An answered card has its link cleared, so a surviving link is a member
        still waiting. The count matters more than it sounds: the whole promise
        is one hour a week, and that only works if the hour is spent on things
        that are actually waiting rather than on checking whether anything is.
        """
        return sum(1 for row in self.store._conn.execute(
            "SELECT value FROM runtime WHERE key LIKE 'esc:%' AND value != ''"))

    def ping_if_questions_are_waiting(self, *, quiet_hours: int = 6) -> bool:
        """Nudge the founders when the community is owed an answer.

        Rate-limited hard. A reminder that arrives every fifteen minutes is
        noise, and noise is how a real alert gets ignored.
        """
        waiting = self.unanswered_questions()
        if not waiting:
            return False

        last = self.store.get_runtime("last_waiting_ping")
        now = now_tashkent()
        if last:
            since = (now - datetime.fromisoformat(last)).total_seconds()
            if since < quiet_hours * 3600:
                return False

        self.store.set_runtime("last_waiting_ping", now.isoformat())
        self._alert(
            f"⏳ <b>{waiting} ta savol</b> sizning javobingizni kutmoqda.\n"
            f"<i>Har biriga shu chatda javob yozsangiz, aʼzoga yetkazaman.</i>"
        )
        log.info("pinged the founders about %s unanswered question(s)", waiting)
        return True

    def _assets_used(self) -> set[str]:
        return {row[0] for row in self.store._conn.execute(
            "SELECT value FROM runtime WHERE key LIKE 'asset_used:%'")}

    def bound_asset(self, content: Content | None):
        """The library asset this content was drafted and approved with, if any."""
        if not content or not content.media_paths:
            return None
        ref = content.media_paths[0]
        return None if ref == CARD else asset_by_id(ref)

    def visual(self, content: Content | None, kind: str, text: str):
        """What accompanies this post: ("asset", Asset), ("card", png), or (None, None).

        A card is not stored, only recorded as a sentinel — the render is
        deterministic, so drawing it at send time is cheaper than managing files
        on a volume and cannot go stale against the text it illustrates.
        """
        asset = self.bound_asset(content)
        if asset:
            return "asset", asset
        if content and CARD in content.media_paths:
            try:
                return "card", cards.render_post(kind, text)
            except Exception:
                # A card is a nice-to-have; the post is not. Never lose a slot
                # to the renderer.
                log.exception("card render failed for %s; falling back to text", kind)
        return None, None

    def _deliver(self, chat_id: int, visual, body: str, *,
                 parse_mode: str | None = None, reply_markup: dict | None = None) -> dict:
        """Send a post — or its preview — as the visual with the words under it."""
        shape, ref = visual
        if shape == "asset":
            sender = self.api.send_video if ref.is_video else self.api.send_photo
            try:
                return sender(chat_id, ref.url, caption=body, parse_mode=parse_mode,
                              reply_markup=reply_markup)
            except TelegramError as exc:
                # Telegram fetches a URL itself, and caps photos sent that way at
                # 5MB — a 2K card crosses that easily, and the only symptom is
                # "failed to get HTTP URL content". Fetching it here and uploading
                # the bytes raises the ceiling to 10MB and also survives a CDN
                # that refuses Telegram's fetcher.
                if ref.is_video:
                    raise
                log.warning("URL send failed (%s); fetching and uploading instead", exc)
                return self.api.upload_photo(
                    chat_id, fetch_image(ref.url), filename=f"{ref.id}.jpg",
                    caption=body, parse_mode=parse_mode, reply_markup=reply_markup)
        if shape == "card":
            return self.api.upload_photo(chat_id, ref, caption=body,
                                         parse_mode=parse_mode, reply_markup=reply_markup)
        return self.api.send_message(chat_id, body, parse_mode=parse_mode,
                                     reply_markup=reply_markup)

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
            self.ensure_media(content, slot)
            self._send_for_approval(content, slot)
        return len(waiting)

    def ensure_media(self, content: Content, slot: Slot) -> None:
        """Bind a visual to content drafted before visuals were bound.

        Anything already in the queue was written when the asset was chosen at
        publish time, so it carries none. Resending those as bare text would
        reproduce the very thing being fixed.
        """
        if content.media_paths or content.frozen:
            return
        asset = pick_asset(content.kind, used=self._assets_used())
        content.attach_media(asset.id if asset else CARD)
        self.store.save_content(content)
        log.info("bound %s to %s on resend", asset.id if asset else "a card", slot.key)

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
