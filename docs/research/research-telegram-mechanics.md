# Telegram Mechanics — Implementation Spec

Target: Bot API **10.2 (released 2026-07-14)**. Server source referenced is `tdlib/telegram-bot-api` master (`CMakeLists.txt`: `project(TelegramBotApi VERSION 10.2 ...)`, commit "Update version to 10.2." dated 2026-07-14) and `tdlib/td` master. Telegram never states that `api.telegram.org` runs the published build — treat exact server-build behavior as LOW confidence where noted.

Constants used below: `CHANNEL_ID` (the broadcast channel), `GROUP_ID` (linked discussion supergroup), `BOT_ID`.

---

## 1. Exact call sequences

### 1.1 Startup: discover and cache the linked group

```
GET /bot<TOKEN>/getChat?chat_id=<CHANNEL_ID>
  -> ChatFullInfo.linked_chat_id        # BIGINT, "may be greater than 32 bits ... smaller than 52 bits"
```
- `linked_chat_id` exists **only on `ChatFullInfo`** (returned by `getChat`). It is **never** on the lightweight `Chat` object embedded in `Message.chat`. `update.message.chat.linked_chat_id` is always `None`.
- Cheaper self-heal route, no API call: any auto-forwarded message gives both ids at once — `message.chat.id == GROUP_ID`, `message.sender_chat.id == CHANNEL_ID` (equivalently `message.forward_origin.chat.id`).

### 1.2 Publish a channel post

```
POST /bot<TOKEN>/sendMessage
  {chat_id: CHANNEL_ID, text: ..., parse_mode: "HTML"}
  -> Message.message_id  == P        # the ONLY way you learn P
```
- **The bot receives NO `channel_post` update for its own post.** `Client::need_skip_update_message()` (Client.cpp ~18561) returns true for `message_info->is_outgoing` on all chat types, hitting `default: return true` before the update type is even chosen. Only a whitelist of service messages survives (`messageChatChangeTitle`, `messageChatChangePhoto`, `messageChatDeletePhoto`, `messageChatDeleteMember`, `messageChatSetTheme`, `messagePinMessage`, `messageProximityAlertTriggered`, `messageVideoChatScheduled/Started/Ended`, `messageInviteVideoChatParticipants`, `messageForumTopic*`, `messageGiveaway*`, `messagePaymentRefunded`, `messageSuggestedPost*`, `messagePollOptionAdded/Deleted`).
- The channel-side `sendMessage` response Message contains **no field pointing at the discussion-group copy**. Correlation must be done by `(CHANNEL_ID, P)` matched against the incoming group message's `forward_origin`.
- Persist `channel_posts(channel_msg_id=P, ...)` immediately after HTTP 200.

### 1.3 Auto-forward detection (the ONLY route to the thread root)

Wait for `Update.message` in `GROUP_ID` matching **all** of:

```
message.chat.id                    == GROUP_ID
message.is_automatic_forward       == true
message.sender_chat.id             == CHANNEL_ID
message.forward_origin.type        == "channel"        # MessageOriginChannel
message.forward_origin.chat.id     == CHANNEL_ID
message.forward_origin.message_id  == P                # the id IN THE CHANNEL — the join key
-> D = message.message_id                              # the thread root id IN THE GROUP
```

- `is_automatic_forward` doc text: *"Optional. True, if the message is a channel post that was automatically forwarded to the connected discussion group"*. Computed server-side as: `forward_info_->source_ != nullptr` AND chat is a Supergroup AND forward source chat is a Channel (Client.cpp 19296-19300). Reposts were wrongly excluded until the fix in Bot API 5.5.1.
- `D` is a **new id with no relationship whatsoever to `P`** — no offset, no formula. `forward_origin.message_id` is the only link.
- `MessageOriginChannel` fields: `type:"channel"`, `date`, `chat` (the channel `Chat`), `message_id`, `author_signature?`.
- **There is NO Bot API way to resolve `P -> D` on demand.** `messages.getDiscussionMessage` ("Get discussion message from the associated discussion group of a channel to show it on top of the comment section, without actually joining the group") is annotated **"Only user accounts can invoke this method"** and has no Bot API equivalent (full 10.2 method list grepped; "discussion" appears only in prose for `linked_chat_id`, `sender_chat`, `is_automatic_forward`, `setMessageReaction`). If the auto-forward update is missed, that post's thread is **permanently unaddressable** by bot credentials — a terminal per-post failure, not a retryable one.
- Timing/ordering of the auto-forward relative to the `sendMessage` HTTP 200 is **undocumented and unguaranteed**. Structural reason it cannot be guaranteed: `messageReplies.replies_pts` is *"PTS of the message that started this thread"* — the group copy is a separate server event in a different dialog's PTS sequence.

### 1.4 First comment

```
POST /bot<TOKEN>/sendMessage
  {chat_id: GROUP_ID,
   text: <Uzbek opening question>,
   parse_mode: "HTML",
   reply_parameters: {"message_id": D}}
```
- **Do NOT send `message_thread_id`.** **Do NOT set `allow_sending_without_reply`.** **Do NOT set `reply_parameters.chat_id`.**
- levlam: *"You don't need to specify message_thread_id, if you want to reply a message that doesn't belong to a topic. Actually, you never need to specify message_thread_id explicitly when replying to a message without allow_sending_without_reply."* Thread placement is inferred server-side from the reply target (`Client::check_reply_parameters` ~9134-9198 → `getMessage`).

### 1.5 Replying to user comments

```
thread_root = message.message_thread_id
              or (message.reply_to_message.message_id if message.reply_to_message.is_automatic_forward)

POST sendMessage {chat_id: GROUP_ID,
                  reply_parameters: {"message_id": <the USER's comment message_id>}}
```
- Replying to **any** message already in the thread keeps you in the thread. Use the user's message id (not `D`) so the reply visually attaches to the person.
- Top-level comments carry `reply_to_message` = the auto-forwarded root object (with `is_automatic_forward: true` inside it), even though MTProto only sends `reply_to_top_id`. Mechanism: `Client::get_reply_to_message_id` falls back to `get_implicit_reply_to_message_id()` (Client.cpp 18768-18773, 19631-19660), which for `td_api::messageTopicThread` returns the thread root when it is smaller than the message id.

### 1.6 Poll lifecycle (channel)

```
POST sendPoll {chat_id: CHANNEL_ID, question, options:[InputPollOption,...], ...}
  -> Message.poll.id                      # persist poll.id -> (chat_id, message_id, campaign)
... Update.poll (aggregate only, cadence undocumented)
POST stopPoll {chat_id, message_id} -> final Poll   # authoritative tally
```
- **`Update.poll` carries ONLY a `Poll` object — no `chat_id`, no `message_id`.** MTProto: *"The updateMessagePoll now includes peer, msg_id, and top_msg_id ... these fields are absent when poll results are pushed to channel subscribers."* The `poll.id` → message map is **mandatory**, not a convenience.

---

## 2. Sender/message classification — ordered decision list

Run **before any LLM sees the message**. Each step is terminal.

1. **Drop** if any service field present: `pinned_message`, `new_chat_members`, `left_chat_member`, `new_chat_title`, `new_chat_photo`, `group_chat_created`, `message_auto_delete_timer_changed`, `video_chat_*`, `forum_topic_*`.
2. `message.is_automatic_forward == true` **AND** `message.sender_chat.id == CHANNEL_ID` → **THREAD ROOT**. Record `D = message.message_id`. Never reply to it as if it were a user; **never delete it**.
3. `from.id == BOT_ID` → drop (defensive; structurally impossible, see §1.2).
4. `sender_chat` present **AND** `sender_chat.id == chat.id` **AND** `from.id == 1087968824` (`@GroupAnonymousBot`) → **anonymous group admin**. `author_signature` = the admin's custom title. Treat as staff, exempt from moderation, allow replies. **No human user id exists anywhere in the update** — no per-user reputation, no ban path.
5. `sender_chat` present **AND** `from.id == 136817688` (`@Channel_Bot`) → **comment posted under a channel identity**. Real content, moderatable **only** via `banChatSenderChat(chat_id, sender_chat_id)` / `unbanChatSenderChat(chat_id, sender_chat_id)`. `restrictChatMember` / `banChatMember` take `user_id` and are useless here. No human user id exposed.
6. `from.id == 777000` and not matched by rule 2 → other Telegram service notification → drop.
7. `from` present and `from.is_bot == false` → **genuine human comment** → route to LLM agents.

### Sender-resolution branch actually implemented by the Bot API server
(Client.cpp 19314-19330) For a message whose sender is a chat, in a non-channel chat:
- `sender_chat_id == chat_id` → `from = group_anonymous_bot_user_id`
- else if `is_automatic_forward` → `from = service_notifications_user_id`
- else → `from = channel_bot_user_id`

### Magic ids (production / test-DC)
| Name | Prod | Test DC | `is_bot` |
|---|---|---|---|
| service notifications (`from` on auto-forwards) | **777000** | 777000 | **false** (`first_name:"Telegram"`, `is_verified`, `is_support`, `phone_number:"42777"`) |
| `@GroupAnonymousBot` | **1087968824** | 552888 | **true** |
| `@Channel_Bot` | **136817688** | 936174 | **true** |
| `@replies` | 1271266957 | 708513 | true |
| anti-spam bot | 5434988373 | 2200583762 | true |

Source: `tdlib/td` `td/telegram/UserManager.cpp` 3019-3049; `Client::JsonUser::store` (Client.cpp 494-495) emits `is_bot` from `user_info->type == UserInfo::Type::Bot`.

**777000 is NOT a protocol constant.** `telegram-bot-api` reads it at runtime from the TDLib option `telegram_service_notifications_chat_id` into `service_notifications_user_id_` (Client.cpp 9789-9792), then assigns it at 19322-19323. Prefer rule 2 (`is_automatic_forward && sender_chat.id == CHANNEL_ID`) over any id match. Read test-DC ids from config if you run integration tests there.

**Never filter on `from.is_bot` to mean "is this a human":** it misclassifies the auto-forward root as human (`is_bot: false`), and drops real humans posting as anonymous admins / as channels (`is_bot: true`).

---

## 3. Polls and quizzes

### Current `sendPoll` signature (10.2, verbatim parameter set)
`business_connection_id, chat_id (req), message_thread_id, question (req, 1-300), question_parse_mode (custom emoji entities ONLY), question_entities, options (req, Array of InputPollOption, 1-12), is_anonymous (default True), type ("quiz"|"regular", default "regular"), allows_multiple_answers (default False), allows_revoting, shuffle_options, allow_adding_options, hide_results_until_closes, members_only, country_codes, correct_option_ids, explanation (0-200 chars, max 2 line feeds after parsing), explanation_parse_mode, explanation_entities, explanation_media (InputPollMedia), open_period, close_date, is_closed, description (0-1024), description_parse_mode, description_entities, media (InputPollMedia), disable_notification, protect_content, allow_paid_broadcast, message_effect_id, reply_parameters, reply_markup`

### Breaking changes vs. pre-2026 knowledge
- **`correct_option_id` NO LONGER EXISTS.** Bot API **9.6 (2026-04-03)** replaced it with **`correct_option_ids` (Array of Integer)** — *"monotonically increasing 0-based identifiers of the correct answer options, required for polls in quiz mode"* — in **both** `sendPoll` and the `Poll` object. Same release allows `allows_multiple_answers` for quizzes. Highest-probability build-breaker in the whole spec.
- `options` is an **Array of `InputPollOption` objects** `{text, text_parse_mode, text_entities, media}`, not strings. Cap is **1-12**, not 1-10.
- `open_period` range is now **5-2628000 seconds (~30.4 days)**, not 5-600 (raised in 9.6). `close_date` must be 5-2628000 s in the future. `open_period` and `close_date` are mutually exclusive ("Can't be used together").

### In channels
- Polls **work** in channels: `chat_id` = *"Unique identifier for the target chat or username of the target bot, supergroup or channel"*. Only stated exclusion: *"Polls can't be sent to channel direct messages chats."*
- Two **channel-only** parameters (new in Bot API 10.0, 2026-05-08):
  - `members_only` — *"voting is limited to users who have been members of the chat ... for more than 24 hours; for channel chats only"* (anti-brigading).
  - `country_codes` — 0-12 ISO 3166-1 alpha-2 codes, `"FT"` for anonymous numbers; *"for channel chats only"*. e.g. `["UZ"]`.
- `sendPoll` accepts `reply_markup`, so an inline keyboard can be attached to a poll message.

### Results and identity
- **Non-anonymous polls do not exist in channels.** Telegram treated client-side creation as a bug (bugs.telegram.org/c/42756, *"Non anonymous polls can be created in channels (without being properly sent)"*, expected *"To not allow non anonymous polls creation in the channel"*, fixed in client 11.1.0.29584, 2024-09-08). Therefore a channel poll produces **zero `poll_answer` updates and no voter identity, ever**.
- `poll_answer` doc: *"A user changed their answer in a non-anonymous poll. Bots receive new votes only in polls that were sent by the bot itself."* `PollAnswer` fields: `poll_id`, `user` (*"if the voter isn't anonymous"*), `voter_chat` (*"if the voter is anonymous"*), `option_ids` (may be empty = retraction), `option_persistent_ids`.
- `voter_chat` is **not** a channel-poll identity mechanism — it fires when a chat votes on its own behalf in a **group** poll.
- `poll` update: *"New poll state. Bots receive only updates about manually stopped polls and polls, which are sent by the bot."* `Poll` carries `total_voter_count`, per-option `voter_count` and `persistent_id`.
- MTProto corroboration of hard anonymity: `messages.getMessageReactionsList` error **403 BROADCAST_FORBIDDEN — "Channel poll voters and reactions cannot be fetched to prevent deanonymization."**
- **Poll-update cadence is undocumented (LOW confidence).** MTProto `core.telegram.org/api/poll` says only *"Regularly, if new users have voted in polls available to the user, they will receive an updateMessagePoll, with updated pollResults."* Pull alternative exists only in MTProto: `messages.getPollResults` with `poll_hash`. The Bot API server does no batching (`td_api::updatePoll::ID` → bare `add_update_poll(...)`), so throttling is entirely server-side and unobservable. Treat live counts as eventually-consistent; use `stopPoll` for the authoritative tally.

### Per-user quiz scoring (the only working route)
Attach `InlineKeyboardMarkup` to the channel post; each tap yields `callback_query` with `from` (User), `data`, `message`, `chat_instance`, `id`. Must call `answerCallbackQuery(callback_query_id, text 0-200, show_alert)` or the user sees a spinner. Trade-off: no native poll UI, no vote bars; render results yourself with `editMessageText`/`editMessageReplyMarkup`.

---

## 4. Reactions — what a channel-admin bot can observe

- Both reaction update types are **opt-in AND admin-gated**:
  - `message_reaction`: *"A reaction to a message was changed by a user. The bot must be an administrator in the chat and must explicitly specify \"message_reaction\" in the list of allowed_updates ... The update isn't received for reactions set by bots."*
  - `message_reaction_count`: *"Reactions to a message with anonymous reactions were changed"*, same admin+opt-in requirement, plus *"The updates are grouped and can be sent with delay up to a few minutes."*
- **In the CHANNEL: aggregate only.** `MessageReactionCountUpdated {chat, message_id, date, reactions: Array of ReactionCount{type: ReactionType, total_count: Integer}}`. Never learns who reacted. MTProto `updateBotMessageReactions`: *"Bots only: the number of reactions on a message with anonymous reactions has changed."*
- **In the DISCUSSION GROUP: named, for ordinary user comments.** `MessageReactionUpdated {chat, message_id, user (Optional — "if the user isn't anonymous"), actor_chat (Optional — "if the user is anonymous"), date, old_reaction, new_reaction: Array of ReactionType}`. This is the only place named per-user engagement signal exists.
- **Reactions on the AUTO-FORWARDED copy inside the group: UNRESOLVED (unverified).** The Bot API sentence *"Automatically forwarded messages from a channel to its discussion group have the same available reactions as messages in the channel"* covers the **emoji set only** ("available reactions" is Telegram's term for the permitted set — cf. `ChatFullInfo.available_reactions`, `messages.setChatAvailableReactions`, `channelFull.reactions_limit`). The anonymity extension traces solely to grammY (non-primary): *"for channel posts, we only have a list of anonymous reactions... The same is true for channel posts that get forwarded to linked discussion group chats automatically."* **Counter-indicator:** TDLib `messageReaction.recent_sender_ids_` — *"Identifiers of at most 3 recent message senders, added the reaction; available in private, basic group and supergroup chats"* — the discussion group IS a supergroup, implying senders ARE resolvable. Empirical test is **mandatory**: subscribe to `message_reaction` AND `message_reaction_count` simultaneously, with the bot as group admin, and react to the auto-forwarded root from a test account.
- **`setMessageReaction(chat_id, message_id, reaction: Array of ReactionType, is_big)`**: *"Currently, as non-premium users, bots can set up to one reaction per message. A custom emoji reaction can be used if it is either already present on the message or explicitly allowed by chat administrators. Paid reactions can't be used by bots."* If the message is in a media group, the reaction lands on the **first non-deleted message** of the group. Bot reactions generate no `message_reaction` update → cannot loop, and cost zero message quota.
- **73-emoji `ReactionTypeEmoji` allowlist** (scraped from docs HTML img alts on 2026-08-12; ordering already changed historically — ❤ now first, was 👍 — re-scrape periodically):
  ❤ 👍 👎 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 ❤‍🔥 🌚 🌭 💯 🤣 ⚡ 🍌 🏆 💔 🤨 😐 🍓 🍾 💋 🖕 😈 😴 😭 🤓 👻 👨‍💻 👀 🎃 🙈 😇 😨 🤝 ✍ 🤗 🫡 🎅 🎄 ☃ 💅 🤪 🗿 🆒 💘 🙉 🦄 😘 💊 🙊 😎 👾 🤷‍♂ 🤷 🤷‍♀ 😡
  Other types: `ReactionTypeCustomEmoji {custom_emoji_id}`, `ReactionTypePaid`. Several are multi-codepoint ZWJ (❤‍🔥, 👨‍💻, 🤷‍♂) and some lack VS16 (🕊, ✍, ☃) — naive Unicode normalization produces rejected calls.
- Moderation: `deleteMessageReaction` (*"remove a reaction from a message in a group or a supergroup chat. The bot must have the can_delete_messages administrator right"*) and `deleteAllMessageReactions` — **group/supergroup only, not channel** (`deleteMessageReaction` added in Bot API 10.2).

---

## 5. Invite links and join attribution (CHANNELS)

- `createChatInviteLink(chat_id, name 0-32, expire_date Unix ts, member_limit 1-99999, creates_join_request Boolean)` — works for channels; bot must be admin with `can_invite_users`. `creates_join_request=True` forbids `member_limit`. Returns `ChatInviteLink {invite_link, creator, creates_join_request, is_primary, is_revoked, name, expire_date, member_limit, pending_join_request_count, subscription_period, subscription_price}`.
- **Attribution is unreliable for PUBLIC chats.** levlam, verbatim:
  - *"No, the parameter works as expected. It is considered if the user joins the chat via the invite link, but for public groups users are free to join them directly, even they opened the group via the invite link."* (issue #429, 2023-06-29 19:33:30)
  - *"The group setting affects only direct joins and each link has separate setting for request creation. If the user joins the group via invite link, then link's settings will be used. But as I told, some apps may try to join public groups always directly."* (2023-06-30 17:42:06)
  - *"The behavior depends on the used app. The official Android app is known to use direct join instead of invite link for public chats."* (issue #428, 2023-06-30 17:38:41)
  - *"I tested this again multiple times and each time the `invite_link` field is present if the user joins the chat using the invite link. I've never managed to reproduce the issue if the chat is joined using the method `messages.importChatInvite`, and apps don't use the method to join public chats and join them directly, hence absence of the field `invite_link` is expected."* (2024-12-02 13:41:13 — "public chats" covers supergroups AND channels)
  - Mechanism: `channels.joinChannel` (username path) vs `messages.importChatInvite` (link path) are different RPCs; the request gate (`channels.toggleJoinRequest` / `request_needed`, which makes `importChatInvite` return `INVITE_REQUEST_SENT`) attaches only to the link path. *"Only supergroups and channels may have a public usernames."*
  - Result: `ChatMemberUpdated.invite_link` absent for most joins, and per-link `creates_join_request=True` silently ineffective (the API still returns `creates_join_request:true`, so the failure is undetectable from the response).
- **There IS a working join gate for a public channel — but it is chat-level, not per-link:** MTProto `channels.toggleJoinRequest` ("Approve New Members" in clients) gates **direct** joins too. Cost: those arrivals produce a `ChatJoinRequest` with **no `invite_link`**, so per-link attribution is lost exactly for the traffic you most want to attribute.
- `ChatMemberUpdated {chat, from, date, old_chat_member, new_chat_member, invite_link (Optional — "Chat invite link, which was used by the user to join the chat; for joining by invite link events only"), via_join_request (Optional — "True, if the user joined the chat after sending a direct join request without using an invite link and being approved by an administrator"), via_chat_folder_invite_link (Optional)}`. Requires bot admin + `"chat_member"` in `allowed_updates`.
- `ChatJoinRequest {chat, from, user_chat_id (REQUIRED), date, bio?, invite_link?, query_id?}`. `user_chat_id`: *"The bot can use this identifier for 5 minutes to send messages until the join request is processed, assuming no other administrator contacted the user."* `chat_join_request` updates require the `can_invite_users` admin right. `approveChatJoinRequest` / `declineChatJoinRequest` take `(chat_id, user_id)`.
- **Join Request Queries — new in Bot API 10.2 (2026-07-14):** `User.supports_join_request_queries` (*"Returned only in getMe"*), `ChatFullInfo.guard_bot`, `ChatJoinRequest.query_id` (*"Identifier of the join request query; for bots assigned to process join requests only. If present, then the bot must call sendChatJoinRequestWebApp or directly call answerChatJoinRequestQuery within 10 seconds"*), `answerChatJoinRequestQuery` (result must be `"approve"`, `"decline"`, or `"queue"`), `sendChatJoinRequestWebApp` (*"process a received chat join request query by showing a Mini App to the user before deciding the outcome"*). **Hard 10-second SLA** the VPS must budget for.
- **No per-link join counter in the Bot API.** `ChatInviteLink` exposes only `pending_join_request_count`. MTProto has `messages.getChatInviteImporters` (*"fetch info about users that joined using a specific invite link"*) and `messages.getAdminsWithInvites`, neither exposed to bots. You must count joins yourself keyed on `invite_link.invite_link`, with no reconciliation endpoint.
- **Robust fallback: bot deep links.** `https://t.me/<bot_username>?start=<PAYLOAD>` delivers `/start PAYLOAD`. Payload charset `A-Z, a-z, 0-9, _ and -`, **max 64 characters** (base64url for binary). Variants `?startgroup=`, `?startapp=`. This is the only attribution path unaffected by direct-join behavior, and it seeds a DM relationship.
- `chat_member` delivery is otherwise reliable. levlam on 15-20% "missing" updates: *"If \"chat_member\" is specified in the list of \"allowed_updates\", which you can check by calling getWebhookInfo, then this can be caused only by using multiple sessions for the bot. If the bot uses multiple sessions, then updates can be missed."*

---

## 6. Rate limits, retry/backoff

**Four** officially published figures (nothing else exists):
1. *"In a single chat, avoid sending more than one message per second. We may allow short bursts that go over this limit, but eventually you'll begin receiving 429 errors."*
2. *"In a group, bots are not be able to send more than 20 messages per minute."*
3. *"For bulk notifications, bots are not able to broadcast more than about 30 messages per second, unless they enable paid broadcasts to increase the limit."* / *"The API will not allow bulk notifications to more than ~30 users per second."*
4. Paid broadcasts: *"By default, all bots are able to broadcast up to 30 messages per second to their users. Developers can increase this limit by enabling Paid Broadcasts in @BotFather - allowing their bot to broadcast up to 1000 messages per second. Each message broadcasted over the free amount of 30 messages per second incurs a cost of 0.1 Stars per message."* Per-call flag: `allow_paid_broadcast` (*"Pass True to allow up to 1000 messages per second, ignoring broadcasting limits for a fee of 0.1 Telegram Stars per message."*)
   - **Telegram's own docs contradict each other on eligibility:** Bot API page says *"at least 10,000 Stars on its balance"*; the FAQ says *"at least 100,000 Stars on its balance and at least 100,000 monthly active users."* Do not encode either. Irrelevant at 3000 members — exclude from the design.

**No channel-specific rate limit is published anywhere.** Grepping the 836 KB Bot API page + FAQ for "per second"/"per minute"/"limit"/"flood" yields no channel figure. The circulating "1 message per 3 seconds for groups and channels" traces to SEO content farms. **Do not hardcode it.**

**429 handling:** response is `{ok:false, error_code:429, description:"Too Many Requests: retry after N"}` plus optional `parameters` of type `ResponseParameters`, whose `retry_after` is *"In case of exceeding flood control, the number of seconds left to wait before the request can be repeated"*. `ResponseParameters` also carries `migrate_to_chat_id`. **Parse `parameters.retry_after`, not the description string.**

**Scope of a 429 is unverified (MEDIUM).** Telegram says only "the request". The claim that a 429 blocks the entire bot token exists only in gramio.dev/rate-limits (*"Your bot is completely blocked for the duration of retry_after"*), which itself labels its numbers approximate. `telegram-bot-api` implements no flood control of its own and merely relays the 429 — scoping is server-side and unobservable. **Safe under either interpretation: pause the WHOLE outbound worker for `retry_after`.**

**Required outbound design:**
- Single centralized sender. Per-chat token bucket at **1 msg/s**; per-group bucket at **20 msg/min**; global ceiling ~**25-30/s**.
- Persist a per-chat cooldown row in Postgres so a restarting worker does not immediately re-trip the flood wait.
- No fixed artificial sleeps — let observed 429s drive backoff.
- Cap the LLM reply agent (e.g. ≤10 replies per thread per hour) plus a global daily cap.
- A self-hosted local Bot API server does **NOT** raise flood limits. levlam: *"The self-hosted Bot API server doesn't affect request flood limits. But even bots with millions users don't exceed limits unless they try to incorrectly use API due to a bug."* It only raises FILE limits (2000 MB upload, unlimited download, local file paths, webhook over HTTP/any port, `max_webhook_connections` up to 100000).

---

## 7. HARD LIMITS that kill or constrain features

1. **Per-user quiz scoring via native channel polls is IMPOSSIBLE** because channel polls are forcibly anonymous (client bug fixed 11.1.0.29584 forbids non-anonymous polls in channels) → zero `poll_answer` updates, no voter identity, ever. Workaround: inline-keyboard `callback_query`.
2. **"Who reacted" in the CHANNEL is IMPOSSIBLE** because channel reactions are anonymous by design — only `message_reaction_count` aggregates arrive; MTProto returns 403 BROADCAST_FORBIDDEN *"to prevent deanonymization"*.
3. **Real-time reaction dashboards are IMPOSSIBLE** because `message_reaction_count` updates are *"grouped and can be sent with delay up to a few minutes"*.
4. **Post view counts / reach / forwards KPIs are IMPOSSIBLE** because no `views`/`view_count`/`forwards` field and no statistics method exists in ~200 Bot API methods; "can access channel statistics" appears only as an admin RIGHT, never as retrievable data.
5. **On-demand lookup of a post's comment thread is IMPOSSIBLE** because `messages.getDiscussionMessage` is *"Only user accounts can invoke this method"* and the Bot API has no equivalent. Architecture must be event-driven; a missed auto-forward update = that post has no addressable comment section, permanently.
6. **Recovering comments after a >24 h outage is IMPOSSIBLE** because the server drops updates whose message date/edit_date is older than 86400 s: `if (message_date <= get_unix_time() - 86400) { ... return true; }` ("don't send messages received/edited more than 1 day ago"). Not replayable.
7. **Learning your own channel post id from an update is IMPOSSIBLE** because `Client::need_skip_update_message` drops all outgoing content messages. You must capture `Message.message_id` from the `sendMessage` response.
8. **Per-link referral attribution on a PUBLIC channel is UNRELIABLE-to-impossible** because clients join public chats directly via `channels.joinChannel`, bypassing the invite link (levlam). Route attribution through bot deep links instead; expect a large honest "direct/unknown" bucket.
9. **Server-side scheduled posting is IMPOSSIBLE** — no `schedule_date`/`send_at` on any send method. The only `send_date` in the API belongs to `approveSuggestedPost(chat_id, message_id, send_date)` (*"must be not more than 2678400 seconds (30 days) in the future"*), which applies only to suggested posts in channel direct-messages chats. The 10:00/21:00 Asia/Tashkent scheduler must be local.
10. **Inline keyboards on albums are IMPOSSIBLE** — `sendMediaGroup(business_connection_id, chat_id, message_thread_id, direct_messages_topic_id, media, disable_notification, protect_content, allow_paid_broadcast, message_effect_id, reply_parameters)` has **no `reply_markup`**. So albums cannot produce `callback_query` attribution. Send album, then a separate keyboard message (second message + second notification).
11. **Deleting spam older than 48 h is IMPOSSIBLE** — *"A message can only be deleted if it was sent less than 48 hours ago."* (`deleteMessages(chat_id, message_ids)` batches 1-100 with the same per-message limit.) Late detection must fall back to banning.
12. **Moderating an anonymous-admin commenter is IMPOSSIBLE** — no human user id in the update, and they are admins.
13. **User-level moderation of comment-as-channel senders is IMPOSSIBLE** — only `banChatSenderChat(chat_id, sender_chat_id)`.
14. **Video >50 MB via the cloud API is IMPOSSIBLE** — multipart limits: *"10 MB max size for photos, 50 MB for other files"*; by HTTP URL: *"5 MB max size for photos and 20 MB max for other types of content"*; by `file_id`: *"There are no limits for files sent this way"*. Photo: ≤10 MB, width+height ≤10000 total, ratio ≤20. `getFile` downloads capped at 20 MB, link *"valid for at least 1 hour"*. Only a local Bot API server lifts this (2000 MB).
15. **Comment-thread bucketing is IMPOSSIBLE if the discussion group has forum mode ON** (see §8.2).
16. **`file_id` is bot-specific and non-transferable** — a staging bot cannot share a media cache with production.

**Not a limit (encode the asymmetry):** editing has **no** time limit. `editMessageText`/`editMessageCaption`/`editMessageMedia`/`editMessageReplyMarkup` carry only *"Note that business messages that were not sent by the bot and do not contain an inline keyboard can only be edited within 48 hours from the time they were sent"* — which does not apply to a bot editing its own channel posts. Use `editMessageText` to publish poll results / refresh leaderboards (no quota, no extra notification).

---

## 8. Startup assertions — refuse to boot

1. `getMe()` → assert `id == BOT_ID`; record `supports_join_request_queries`.
2. `getChat(CHANNEL_ID)` → assert `linked_chat_id` present and `== GROUP_ID`. If absent → **no linked group; refuse**.
3. `getChat(GROUP_ID)` → assert **`is_forum` absent/false**. (`Client.cpp:1303` emits `"is_forum": true` only when `supergroup_info->is_forum`.) If true → **refuse**: comment threading is unroutable (§8.2 / §9).
4. `getChatMember(CHANNEL_ID, BOT_ID)` → status `administrator`, assert `can_post_messages`, `can_edit_messages`, `can_delete_messages`, `can_invite_users`.
   - `can_post_messages`: *"True, if the administrator can post messages in the channel, approve suggested posts, or access channel statistics; for channels only"*.
   - `can_edit_messages`: *"can edit messages of other users and can pin messages; for channels only"* (also the right required to **pin in a channel**: *"the bot must be an administrator with the can_pin_messages right or the can_edit_messages right to pin messages in groups and channels respectively"*; pin notifications *"are always disabled in channels and private chats"*).
5. `getChatMember(GROUP_ID, BOT_ID)` → status `administrator`, assert `can_delete_messages`, `can_restrict_members`, `can_pin_messages`, `can_invite_users`, `can_manage_chat` (*"Implied by any other administrator privilege"*; grants ignore-slow-mode and see-hidden-members).
6. `getWebhookInfo()` → assert `allowed_updates` **exactly equals** the intended list. `allowed_updates` **persists**: *"If not specified, the previous setting will be used."* Re-issue `setWebhook` on every deploy.
7. Assert the client library exposes **`correct_option_ids`** (not `correct_option_id`) on its Poll/sendPoll model → else refuse (wrong library pin).
8. Assert single-consumer: acquire a Postgres advisory lock (or systemd single-instance unit). Duplicate sessions silently drop updates (levlam).
9. Assert all chat/user ids are stored as **BIGINT / int64** — ids exceed 32 bits (`-100xxxxxxxxxx` supergroups); the docs explicitly warn about *"difficulty/silent defects"* in 32-bit-int languages.
10. Audit and log (do not necessarily refuse) `getChat(GROUP_ID)`: `join_to_send_messages` (*"True, if users need to join the supergroup before they can send messages"*), `join_by_request`, `slow_mode_delay` (*"the minimum allowed delay between consecutive messages sent by each unprivileged user; in seconds"*), `unrestrict_boost_count`, `has_visible_history`, `has_aggressive_anti_spam_enabled`, `permissions.can_send_messages`. **`join_to_send_messages == true` is the most likely cause of a quiet linked group** — non-members hit MTProto `CHAT_GUEST_SEND_FORBIDDEN`. Highest-ROI single fix; alert loudly at boot if set.
11. Operator runbook (no API equivalent): BotFather `/setprivacy` → **Disable** (UI label "Group Privacy"); keep **Bot-to-Bot Communication Mode OFF**; keep Guest Mode OFF. *"Privacy mode is enabled by default for all bots, except bots that were added to a group as admins (bot admins always receive all messages)."* Flipping `/setprivacy` after the bot joined requires re-adding it — *"the bot will need to be re-added to the group for this change to take effect"* — so **admin status is the reliable lever**.
12. `setWebhook` config: `{url: "https://<vps>/tg/<random-path>", secret_token: <32 chars, [A-Za-z0-9_-], 1-256>, max_connections: 10-20 (range 1-100, default 40), allowed_updates: [...], drop_pending_updates}`. Ports **443, 80, 88, 8443 only**. Verify the `X-Telegram-Bot-Api-Secret-Token` header on every request. `getUpdates` and webhooks are mutually exclusive.
13. `allowed_updates` to set explicitly (defaults **exclude** `chat_member`, `message_reaction`, `message_reaction_count` — *"Specify an empty list to receive all update types except chat_member, message_reaction, and message_reaction_count (default)"*):
    `["message","edited_message","channel_post","edited_channel_post","callback_query","poll","poll_answer","message_reaction","message_reaction_count","chat_member","my_chat_member","chat_join_request","chat_boost","removed_chat_boost"]`
    Full 2026 update-type universe: `message, edited_message, channel_post, edited_channel_post, business_connection, business_message, edited_business_message, deleted_business_messages, guest_message, message_reaction, message_reaction_count, inline_query, chosen_inline_result, callback_query, shipping_query, pre_checkout_query, purchased_paid_media, poll, poll_answer, my_chat_member, chat_member, chat_join_request, chat_boost, removed_chat_boost, managed_bot, subscription`.
14. Library pin: **aiogram ≥ 3.30.0** is the only major Python library declaring Bot API 10.2 today (python-telegram-bot 22.8 = 10.0; pyTelegramBotAPI 4.36.0 = 10.1). All three post-date 9.6 and carry `correct_option_ids`; an older pinned version does not.

### 8.1 Postgres schema (minimum)
```
channel_posts(channel_msg_id BIGINT PK, group_root_msg_id BIGINT UNIQUE NULL,
              posted_at TIMESTAMPTZ, slot TEXT,
              first_comment_msg_id BIGINT NULL, first_comment_state TEXT)
comments(group_msg_id BIGINT PK, thread_root BIGINT REFERENCES channel_posts(group_root_msg_id),
         from_user_id BIGINT NULL, sender_chat_id BIGINT NULL, is_anonymous_admin BOOL,
         text TEXT, created_at TIMESTAMPTZ, replied_msg_id BIGINT NULL)
polls(poll_id TEXT PK, chat_id BIGINT, message_id BIGINT, campaign TEXT, ...)
processed_updates(update_id BIGINT PK)
banned_sender_chats(sender_chat_id BIGINT PK)
chat_cooldowns(chat_id BIGINT PK, retry_until TIMESTAMPTZ)
member_counts(chat_id BIGINT, at TIMESTAMPTZ, count INT)   -- hourly getChatMemberCount
media_cache(sha256 TEXT PK, file_id TEXT)
```
Idempotency: return HTTP 200 immediately, enqueue, dedupe on `update_id`. `UNIQUE` on `channel_posts.group_root_msg_id`; first-comment job = conditional `UPDATE ... WHERE first_comment_state='pending' RETURNING`. The auto-forward handler must **upsert** on `channel_msg_id` (the auto-forward update can arrive before the scheduler's INSERT commits). Reconciliation job: scan `group_root_msg_id IS NULL` older than N minutes → alert (comments disabled or link broken). Timeout policy: 120 s window tracked in Postgres, then `first_comment_state='no_thread'` + alert — **never** fall back to posting into the group's main flow.

### 8.2 Forum mode on the discussion group — determined, must be OFF
Source chain: `MessageTopic` ctor (td/telegram/MessageTopic.cpp), Channel branch, evaluated **before** the megagroup/Thread branch:
`if (is_forum_channel(channel_id) && !is_topic_message) { type_ = Type::Forum; forum_topic_id_ = ForumTopicId::general(); return; }`. Comment-thread messages have `is_topic_message == false` (levlam: a thread *"is a forum topic only if message.is_topic_message == true"*), so **every comment collapses to the General topic**. The Bot API then discards it: `Client.h:69 static constexpr int32 GENERAL_FORUM_TOPIC_ID = 1;` and `Client::get_forum_topic_id` (Client.cpp 19684-19690) returns 0 for General; `Client.cpp:4762-4765` emits the field only when non-zero.
**Consequence:** in a forum discussion group, incoming comments arrive with **no `message_thread_id` and no `is_topic_message`** — thread identity is erased from the payload; per-post comment routing breaks. Send-side `message_thread_id=1` hard-fails: `Client.cpp:8937-8940` → `fail_query(400, "Bad Request: message thread not found")`. Reply-based threading via `reply_parameters.message_id` still works (it does not consult `message_thread_id`), but you lose incoming bucketing.
*(Still unknown, LOW: whether Telegram's server routes the auto-forwarded post into General vs a real topic, and whether it sets `top_msg_id` on comments in a forum discussion group. `core.telegram.org/api/forum` never mentions linked discussion groups, `channels.setDiscussionGroup`, or comment sections.)* (unverified)

---

## 9. Traps — silent wrong behavior in front of 3000 members

1. **`message_thread_id` on send is a silent no-op in a non-forum discussion group.** `Client::check_message_topic` (Client.cpp ~8918-8954) sets `can_be_forum` only when `supergroup_info->is_forum` (or chat is Private); otherwise `return on_success(chat_id, nullptr, std::move(query));` — the topic is dropped, **no error**. Your "first comment" lands in the group's main flow, visible to everyone, not under the post.
   **This behavior is NEW in Bot API 10.0 (2026-05-08) and UNDOCUMENTED** (the 10.0 changelog covers guest mode — `guest_bot_caller_user`, `guest_bot_caller_chat`, `guest_query_id`, `guest_message`, `SentGuestMessage`, `answerGuestQuery` — and says nothing about message threads). Three different outcomes depending on server build:
   - Bot API **6.3** (commit `571baeead026fd6c671e00d6c5cf76d2bdf8eeb1`, Nov 2022): `check_message_thread` had **no forum check** — the value **was honored** for non-forum supergroups.
   - Bot API **7.0 / 8.0 / 9.0** (`CC_7.0.cpp:4198-4202`, `CC_8.0.cpp:5173-5177`, `CC_9.0.cpp:5719-5723`): **hard 400** `MESSAGE_THREAD_INVALID` — "Message thread not found" / "Message thread is not a forum topic thread".
   - Bot API **10.0+** (commit `01a3679c0bbf9bbba03d1d3e20f621fa4becddcc`, `CC_10.0.cpp:8256-8288`): silent drop; grep for `MESSAGE_THREAD_INVALID` returns **zero hits** in 10.0 and master. Real-world rollout report: tdlib/telegram-bot-api issue **#847** ("sendMessage with message_thread_id fails for private chat topics after Bot API 10.0 rollout"), degradation window ~**12:07-14:38 UTC on 2026-05-08**.
   **→ Never send `message_thread_id`. `reply_parameters.message_id` is stable across 6.3 → 10.2.**
2. **`allow_sending_without_reply: true` converts a missing root into a stray group message** instead of an error. Always omit it for anything that must be a comment; let the 400 surface and retry. Doc: *"Always False for replies in another chat or forum topic."*
3. **`reply_parameters.chat_id = <channel>` from within the group does NOT create a comment.** It dispatches a different TDLib constructor — `Client::get_input_message_reply_to` (Client.cpp 10087-10101): `if (reply_parameters.reply_in_chat_id != 0) { return make_object<td_api::inputMessageReplyToExternalMessage>(...); } return make_object<td_api::inputMessageReplyToMessage>(...);` — which cannot confer thread membership. Receive side round-trips as `external_reply` (*"Information about the message that is being replied to, which may come from another chat or forum topic"*) + `quote`. Confidence HIGH (source-traced); no test needed. Never use it.
4. **Never read `message_thread_id` off the auto-forwarded root.** When present it equals the root's own `message_id` (chain: `MessagesManager::fix_message_topic()` assigns `m->top_thread_message_id = message_id` when `!m->reply_info.is_empty() || m->reply_info.was_dropped()`; `MessageReplyInfo` ctor for bots always sets `is_dropped_ = true` via `if (is_bot || reply_info->channel_id_ == 777) { is_dropped_ = true; return; }`, and the `|| was_dropped()` disjunct exists specifically so bots still get it; `MessageTopic` → `messageTopicThread` → `Client::get_forum_topic_id` at Client.cpp:19677 → emitted at 4762-4765). **But whether Telegram attaches the MTProto `messageReplies` constructor to a freshly auto-forwarded post with zero comments is undocumented — the field may be absent entirely.** (unverified) Always store `root_message_id = message.message_id` at `is_automatic_forward` receipt.
5. **Never delete a message with `is_automatic_forward == true`.** *"The comment section of a particular post can be disabled by removing the auto-forwarded channel post message from the discussion group."* Deleting it permanently kills comments for that post.
6. **Album channel posts create MULTIPLE auto-forwarded messages at once**, sharing one `media_group_id`. Picking the wrong one as root yields a comment nested inside the thread rather than the clean first comment. Debounce ~1-2 s on `media_group_id` and take the **lowest `message_id`**. (medium confidence — inferred from `media_group_id` semantics + the `setMessageReaction` "first non-deleted message in the group" rule; no direct statement about discussion groups)
7. **Album caption rule is "exactly one", not "first".** `core.telegram.org/api/files`: *"For photo albums, clients should display an album caption only if exactly one photo in the group has a caption, otherwise no album caption should be displayed, and only when viewing in detail a specific photo of the group the caption should be shown. Other grouped media can display a caption under each file."* Adding a caption to a second item **suppresses the album caption entirely**. Photo albums only; document/audio groups show per-file captions. It is client-rendering guidance ("clients should display"), not a server guarantee. `sendMediaGroup` requires **2-10 items**.
8. **Expect ~2 non-comment updates per channel post in the group**: the auto-forward, plus the auto-pin service message (*"those messages will also be automatically pinned in the group"*) carrying `Message.pinned_message` (`MaybeInaccessibleMessage`). Bots receive all service messages regardless of privacy mode. Filter both before any LLM sees the stream.
9. **`from.id == 777000` is not exclusive to auto-forwards** — it also carries other Telegram service notifications. Always pair with `is_automatic_forward == true`.
10. **Do not filter on `from.is_bot`.** 777000 is `is_bot: false`; 1087968824 and 136817688 are `is_bot: true` but represent real human posts.
11. **BotFather "Bot-to-Bot Communication Mode" would let your LLM answer other bots** — unbounded loop with real token cost. Default is off: *"Bots talking to each other could potentially get stuck in unwelcome loops. To avoid this, we decided that bots will not be able to see messages from other bots regardless of mode."* Telegram warns: *"Failure to handle loops properly may lead to degraded performance or platform restrictions."* Keep OFF.
12. **`allowed_updates` silently reverts to the previous stored list** if you ever call `setWebhook`/`getUpdates` without it. `chat_member` / `message_reaction` / `message_reaction_count` require **both** explicit listing **and** bot admin — missing either yields silent absence, not an error.
13. **Your own `setMessageReaction` calls do not echo back** (*"The update isn't received for reactions set by bots"*) — track them in your own DB.
14. **Duplicate bot sessions silently drop updates** (two workers on one token, or a leftover webhook plus polling).
15. **Any cleanup job that deletes must run well inside 48 h** or it silently fails. Edits are forever; deletes expire.
16. **Naive Unicode normalization of reaction emoji produces rejected `setMessageReaction` calls** (ZWJ sequences and missing VS16).
17. **Comment-as-channel spam is the standard vector in open comment sections.** Needs a separate code path keyed on `sender_chat.id` + `banned_sender_chats` table.

---

## 10. What did NOT survive verification

**REFUTED — drop these entirely:**

- ~~"Whether user 777000 is flagged `is_bot` is unverified; don't assume either way."~~ → **`is_bot == false`, definitively.** `UserManager::get_user_force()` initializes `bool is_bot = false;` and the service-notifications branch does not set it (it sets `is_verified = true; is_support = true; first_name = "Telegram"; phone_number = "42777";`), unlike the sibling branches for `replies_bot`, `channel_bot`, `anti_spam_bot`, `anonymous_bot` which do. A classifier treating `is_bot` as "is this a human" **will misclassify the auto-forward root as human**.
- ~~"777000 is a protocol constant to hardcode."~~ → It is read at runtime from the TDLib option `telegram_service_notifications_chat_id` ("Identifier of the Telegram Service Notifications chat"). Key on `is_automatic_forward && sender_chat.id == CHANNEL_ID` instead.
- ~~"Forum-mode-on-discussion-group behavior is unknown; verify empirically."~~ → **Fully determined in source** (§8.2). Not "prefer off" — must be OFF, and asserted at boot.
- ~~"Whether a bot receives a `channel_post` update for its own posts is unknown (low confidence)."~~ → **It definitively does not.** `Client::need_skip_update_message` drops all outgoing content messages before the update type is chosen. Confidence LOW → HIGH.
- ~~"Album caption: a single caption on the FIRST item becomes the album caption; undocumented."~~ → **Documented, and the rule is different**: exactly-one-caption, position irrelevant (§9.7). Confidence MEDIUM → HIGH for the corrected formulation.
- ~~"Older self-hosted Bot API servers may still ACCEPT `message_thread_id` for non-forum supergroups."~~ → Only **6.3-era** builds accept it; **7.0 through 9.x REJECT with 400 `MESSAGE_THREAD_INVALID`**; 10.0+ silently drops (§9.1).
- ~~"Only three official rate-limit figures exist."~~ → **Four** (paid broadcast 1000/s at 0.1 Stars/msg), and Telegram's own two pages contradict each other on the Stars threshold (10,000 vs 100,000).

**CONFIRMED but with the reasoning corrected / strengthened:**
- Cross-chat `reply_parameters.chat_id` → external reply, not a comment: MEDIUM → **HIGH**, source-traced (`inputMessageReplyToExternalMessage`). The "test it once" advice is unnecessary.
- Root's `message_thread_id` == own `message_id`: the mechanism is **high** confidence (full source chain traced), but **field presence on a zero-comment root is LOW confidence** — the real risk the original reasoning missed. Never read it off the root.
- Auto-forward timing undocumented: CONFIRMED, plus the hardening that there is **no polling recovery path at all** (bots cannot call `messages.getDiscussionMessage`), making a missed auto-forward a permanent per-post failure.
- `creates_join_request` bypass on public channels: CONFIRMED, plus the correction that a **chat-level** join gate (`channels.toggleJoinRequest`) does work on direct joins — at the cost of losing `invite_link` on exactly those requests.

**STILL UNVERIFIED (keep, marked):**
- Anonymity of reactions on the auto-forwarded copy inside the discussion group. Primary docs are silent; grammY asserts anonymity; TDLib `recent_sender_ids_` implies the opposite for supergroups. **Must test empirically before any engagement-scoring logic depends on it.** (unverified)
- `poll` update delivery cadence for a live anonymous channel poll. (unverified, LOW)
- Whether a 429 blocks the whole token or only the offending chat. (unverified, MEDIUM — mitigate by pausing the whole outbound worker)
- Whether `api.telegram.org` matches `telegram-bot-api` master byte-for-byte; the `message_thread_id` silent-ignore was not empirically tested against the live cloud API. Validate with a throwaway channel+group. (unverified, LOW)
- Album auto-forward → multiple roots, lowest `message_id` is the thread root. (medium)
- Whether `channel_post.from` is populated when a channel has "Sign messages" + "Show authors' profiles" enabled. Docs only guarantee `author_signature` and say `from` *"may be empty for messages sent to channels"*. **Do not build author attribution on `channel_post.from`.** (unverified)
- Forum-mode discussion group: server-side routing of the auto-forwarded post and `top_msg_id` on comments. (unverified, LOW)

---

## Surprises

- **The channel post id and its discussion-group root id are unrelated integers with no lookup API.** The single most load-bearing fact in the design; it forces a fully event-driven architecture with a Postgres join table.
- **Sending with `message_thread_id` to a linked discussion group changed semantics three times** (honored → hard 400 → silent drop) and the current silent-drop behavior, shipped 2026-05-08, is **undocumented**. An undocumented silent-failure change can silently revert.
- **The bot never sees its own channel post**, so the "obvious" design (react to `channel_post`) is structurally impossible.
- **`Update.poll` has no chat_id or message_id.** Naive code cannot tell which poll it is about.
- **`correct_option_id` no longer exists** — every pre-2026 quiz snippet is broken.
- **`open_period` ceiling jumped from 600 s to 2,628,000 s.**
- **777000 reports `is_bot: false`** — the auto-forward root looks like a human named "Telegram".
- **A public channel makes invite-link referral attribution mostly useless**, per the Bot API's own maintainer, and the failure is undetectable from the API response (`creates_join_request: true` is still echoed back).
- **Reactions and polls in the channel are structurally anonymous** (MTProto literally says "to prevent deanonymization"), so all named gamification must live in the discussion group — which conveniently is also the thing you want to un-quiet.
- **A quiet linked group is more likely a config problem (`join_to_send_messages`) than a content problem.**
- **A >24 h outage permanently destroys comment updates** — the server, not the client, drops them.
- **Bot API 10.2 shipped a 10-second SLA** (`ChatJoinRequest.query_id` → `answerChatJoinRequestQuery`) that a VPS scheduler must be able to meet.
- **`can_edit_messages`, not `can_pin_messages`, is the pin right in a channel.**

## Open questions

1. Are reactions on the auto-forwarded root in the discussion group attributable (`message_reaction.user`) or anonymous (`message_reaction_count`)? Determines whether reaction-based gamification can key on the post at all. Test: bot admin in group, both update types in `allowed_updates`, react from a test account.
2. Does the auto-forwarded root actually carry `message_thread_id` when it has zero comments? Capture a real payload.
3. Does live `api.telegram.org` silently drop `message_thread_id` for a non-forum supergroup, or still 400? Throwaway channel + group.
4. Is a 429 scoped to the chat or the token?
5. Measured distribution of auto-forward latency after `sendMessage(CHANNEL_ID)` — instrument in production; needed only to tune the 120 s timeout, not for correctness.
6. `poll` update cadence for a live channel poll — measure, or just rely on `stopPoll`.
7. For album channel posts, is the thread root always the lowest `message_id` in the `media_group_id`?
8. Which Stars threshold for paid broadcasts is real (10,000 vs 100,000)? Academic at 3000 members.
9. In a forum-mode discussion group, where does Telegram route the auto-forwarded post? Only matters if forum mode is ever forced on.
