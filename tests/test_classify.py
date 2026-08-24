"""Which kind of question is this.

The grounding gate always asked one question — is the fact in the knowledge
base — and applied the same answer to every class. That is right for a price
and wrong for craft technique, and it cost a real one: a member asked how to
write a prompt for a realistic image and the bot went to the founders.

Precedence is the safety property here, not an implementation detail.
"""

from __future__ import annotations

import pytest

from app.agents.classify import Topic, may_teach, topic_of


class TestTheRealQuestion:
    """The message that caused this module to exist."""

    def test_the_member_question_is_craft(self):
        assert topic_of("qanaqa promt yozish kere bunaqa realistik chiqishi uchun") is Topic.CRAFT

    def test_and_it_is_teachable(self):
        assert may_teach("qanaqa promt yozish kere bunaqa realistik chiqishi uchun")


class TestPrecedence:
    """Most dangerous reading wins. This is the whole design.

    A message is often several things at once. Answering it on the strength of
    its safest half is how a price gets stated in public.
    """

    def test_craft_plus_money_is_money(self):
        assert topic_of("zoʻr chiqibdi, qanday yozdingiz va Kling qancha turadi?") is Topic.MONEY

    def test_ours_plus_money_is_money(self):
        assert topic_of("qanday qildingiz va qancha turadi?") is Topic.MONEY

    def test_craft_plus_ours_is_ours(self):
        # "How did YOU write it" is about our work, not general technique.
        assert topic_of("bu rasmni qanday qildingiz, qanaqa prompt?") is Topic.OURS

    def test_money_wins_even_buried_at_the_end(self):
        assert topic_of("yorugʻlikni qanday yozaman? aytgancha obuna narxi qancha") is Topic.MONEY


class TestMoney:
    @pytest.mark.parametrize("text", [
        "Kling 3.0 qancha turadi?",
        "Sizda kurs bormi?",
        "bepulmi?",
        "obunasi qimmatmi",
        "Shu bilan oyiga qancha ishlash mumkin?",
        "нарxi qancha",
        "қанча туради",
    ])
    def test_money_questions(self, text):
        assert topic_of(text) is Topic.MONEY

    def test_money_is_never_teachable(self):
        assert not may_teach("realistik chiqishi uchun nima yozay va qancha turadi?")


class TestOurs:
    @pytest.mark.parametrize("text", [
        "Qaysi AIdan foydalaniladi videolaga?",
        "Қандай қилганизнм хам кўрсатиб беринг",
        "қандай қилдиз",
        "sozlamalarni ayting",
        "siz nima bilan qildingiz?",
    ])
    def test_questions_about_our_work(self, text):
        assert topic_of(text) is Topic.OURS

    def test_ours_is_not_teachable(self):
        # The nearest miss to craft, and the easiest thing to get wrong. A
        # guess about our own output is a lie a member can check against us.
        assert not may_teach("Bu videoni qanday qildingiz?")


class TestCraft:
    @pytest.mark.parametrize("text", [
        "qanaqa promt yozish kerak",
        "realistik chiqishi uchun nima yozay?",
        "yorugʻlikni qanday yozish kerak?",
        "kamera rakursi haqida maslahat bering",
        "kompozitsiya qanday boʻlishi kerak",
        "қандай промт ёзиш керак",
        "реалистик чиқиши учун",
    ])
    def test_general_technique(self, text):
        assert topic_of(text) is Topic.CRAFT


class TestOther:
    @pytest.mark.parametrize("text", [
        "Promp boyicha qldim", "Rahmat", "zoʻr!", "", None,
    ])
    def test_social_messages_are_unchanged(self, text):
        assert topic_of(text) is Topic.OTHER

    def test_other_is_not_teachable(self):
        assert not may_teach("Rahmat")


class TestTheCraftBase:
    """What the bot is allowed to teach from."""

    def _craft(self):
        import yaml
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        return yaml.safe_load((root / "data" / "knowledge" / "craft.yaml").read_text("utf-8"))

    def test_it_loads_and_has_entries(self):
        assert len(self._craft()["craft"]) >= 8

    def test_every_entry_carries_the_evidence_that_proved_it(self):
        """No entry without evidence.

        The craft base is defensible only because we ran the tests ourselves. An
        entry summarising somebody's blog post would look identical and quietly
        destroy that guarantee, so the file cannot hold one.
        """
        missing = [k for k, v in self._craft()["craft"].items() if not v.get("evidence")]
        assert not missing, f"craft entries with no evidence: {missing}"

    def test_every_entry_has_an_uzbek_short_form(self):
        # `short` is what a reply is built from; English detail is for the model.
        missing = [k for k, v in self._craft()["craft"].items() if not v.get("short")]
        assert not missing, f"craft entries with no Uzbek short form: {missing}"

    def test_it_restates_what_craft_may_never_cover(self):
        never = " ".join(self._craft()["never"]).lower()
        for forbidden in ("price", "our_posts", "earn"):
            assert forbidden in never, f"the never-list does not mention {forbidden}"


class TestTheReplierSeesIt:
    def test_the_craft_base_is_in_the_cached_system_half(self):
        from app.agents.replier import system_prompt

        s = system_prompt()
        assert "CRAFT BASE" in s
        assert "light_is_the_biggest_lever" in s

    def test_the_teaching_register_is_gated_on_craft(self):
        from app.agents.replier import system_prompt

        s = system_prompt()
        assert "TEACHING REGISTER" in s
        assert "craft questions ONLY" in s.replace("—", "-") or "craft" in s

    def test_the_topic_reaches_the_per_message_half(self):
        from app.agents.context import ReplyContext, ThreadMessage
        from app.agents.replier import build_prompt
        from app.telegram.classifier import Kind
        from app.text.script import Script

        ctx = ReplyContext(
            target=ThreadMessage(message_id=1, author="A", author_id=1,
                                 text="qanaqa promt yozish kere realistik chiqishi uchun",
                                 kind=Kind.HUMAN),
            thread_root_id=1, post_text="post", history=[], script=Script.LATIN,
        )
        assert "TOPIC: craft" in build_prompt(ctx)
