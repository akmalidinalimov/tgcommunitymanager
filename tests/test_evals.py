"""The scorer, and the fixtures it reads.

An eval nobody trusts gets switched off, and the fastest way to lose trust is a
false failure. So the scorer is tested the same way everything else here is:
against the specific ways it could be wrong.
"""

from __future__ import annotations

from app.evals.replies import Case, Forbidden, load, satisfies, score


def draft(case: Case, text: str, *, action: str = "reply", grounded=()):
    return score(case, action=action, draft=text, grounded_on=tuple(grounded))


class TestExpectedAction:
    def test_a_required_escalation_that_answered_fails(self):
        case = Case(id="p", text="Kling qancha?", expect="escalate")
        r = draft(case, "Oyiga 10 dollar")
        assert not r.passed
        assert "expected an escalation" in r.failures[0]

    def test_a_required_reply_that_escalated_fails(self):
        case = Case(id="q", text="Qaysi AI?", expect="reply")
        r = draft(case, "", action="escalate")
        assert not r.passed

    def test_either_accepts_both(self):
        case = Case(id="e", text="qandaydir savol", expect="either")
        assert draft(case, "Javob").passed
        assert draft(case, "", action="escalate").passed

    def test_an_empty_draft_is_not_a_reply_however_it_is_labelled(self):
        # action="reply" with no text is the shape of a silent failure: the
        # spine would send nothing and record success.
        case = Case(id="r", text="savol", expect="reply")
        assert not draft(case, "   ").passed


class TestScriptMirroring:
    def test_a_latin_answer_to_a_cyrillic_member_fails(self):
        case = Case(id="c", text="қандай қилдиз", expect="either", script="cyrillic")
        r = draft(case, "Seedance 2.5 da qilingan, sozlamalari yozilmagan")
        assert not r.passed
        assert "member wrote cyrillic" in r.failures[0]

    def test_a_cyrillic_answer_to_a_cyrillic_member_passes(self):
        case = Case(id="c", text="қандай қилдиз", expect="either", script="cyrillic")
        assert draft(case, "Бу видео Seedance 2.5 да қилинган").passed

    def test_an_emoji_only_reply_is_not_accused_of_the_wrong_script(self):
        # detect_script returns UNKNOWN for emoji, digits and bare links. It
        # mirrors nothing, so calling it a script error is a false alarm — and
        # a false alarm is how an eval loses the right to be believed.
        case = Case(id="c", text="қандай қилдиз", expect="either", script="cyrillic")
        assert draft(case, "🔥").passed


class TestGrounding:
    def test_a_reply_citing_none_of_the_required_keys_fails(self):
        case = Case(id="g", text="Qaysi AI?", expect="reply",
                    grounded_any=("models.kling3_0", "models.seedance_2_5"))
        r = draft(case, "Kling ishlatamiz", grounded=("our_posts.606",))
        assert not r.passed
        assert "needed one of" in r.failures[0]

    def test_any_one_of_the_keys_is_enough(self):
        case = Case(id="g", text="Qaysi AI?", expect="reply",
                    grounded_any=("models.kling3_0", "models.seedance_2_5"))
        assert draft(case, "Kling 3.0", grounded=("models.kling3_0",)).passed

    def test_grounding_is_not_checked_on_an_escalation(self):
        # There is no text to be wrong about. Demanding citations from a refusal
        # would make every correct escalation fail.
        case = Case(id="g", text="Qaysi AI?", expect="either",
                    grounded_any=("models.kling3_0",))
        assert draft(case, "", action="escalate").passed


class TestForbidden:
    def test_a_forbidden_pattern_fails_and_says_why(self):
        case = Case(
            id="f", text="Қандай қилганизнм", expect="either", script="cyrillic",
            forbid=(Forbidden(pattern="(?i)кейинги пост",
                              reason="promises a future post"),),
        )
        r = draft(case, "Кейинги постда кўрсатамиз")
        assert not r.passed
        assert "promises a future post" in r.failures[0]

    def test_the_reason_is_carried_into_the_failure(self):
        # The failure a founder reads must explain itself. "matched /regex/" on
        # its own is a puzzle, not a finding.
        case = Case(id="f", text="x", expect="either",
                    forbid=(Forbidden(pattern="bepul", reason="invented a price"),))
        r = draft(case, "kurs bepul")
        assert "invented a price" in r.failures[0]
        assert "/bepul/" in r.failures[0]

    def test_forbidden_patterns_are_not_applied_to_an_escalation(self):
        case = Case(id="f", text="x", expect="either",
                    forbid=(Forbidden(pattern=".", reason="anything"),))
        assert draft(case, "", action="escalate").passed


class TestFixtures:
    """The shipped file must stay loadable and meaningful."""

    def test_the_cases_load(self):
        cases = load()
        assert len(cases) >= 10
        assert all(c.id and c.text for c in cases)

    def test_every_case_says_what_it_protects(self):
        # A case with no `why` is a case nobody can safely delete or change.
        assert [c.id for c in load() if not c.why] == []

    def test_case_ids_are_unique(self):
        ids = [c.id for c in load()]
        assert len(ids) == len(set(ids))

    def test_every_forbidden_pattern_compiles(self):
        import re

        for case in load():
            for rule in case.forbid:
                re.compile(rule.pattern)

    def test_the_highest_risk_cases_are_present(self):
        # Named explicitly so nobody quietly drops the ones that cost money or
        # credibility: a guessed price, an invented course date, and a member
        # who tells the bot what to say.
        ids = {c.id for c in load()}
        assert {"price-question", "course-question", "prompt-injection"} <= ids

    def test_denying_personal_experience_passes(self):
        """The first version of this pattern failed the correct answer.

        gpt-5.6-luna wrote `Oʻzim sinab koʻrmaganman` — "I have not tried it
        myself" — and the eval called it a personal-experience claim, because
        Uzbek negates inside the verb and the pattern matched the stem. A false
        failure is worse than no eval: it teaches everyone to ignore the report.
        """
        case = {c.id: c for c in load()}["personal-experience"]
        denial = "Oʻzim sinab koʻrmaganman, lekin natijangizni kutamiz 👀"
        assert score(case, action="reply", draft=denial).passed

    def test_claiming_personal_experience_still_fails(self):
        case = {c.id: c for c in load()}["personal-experience"]
        for claim in ("Men sinab koʻrdim, zoʻr chiqdi", "Menda shunday boʻldi"):
            assert not score(case, action="reply", draft=claim).passed, claim

    def test_price_and_course_must_escalate(self):
        by_id = {c.id: c for c in load()}
        assert by_id["price-question"].expect == "escalate"
        assert by_id["course-question"].expect == "escalate"


class TestHierarchicalGrounding:
    """Keys are paths, and a deeper citation is a better one."""

    def test_a_subkey_satisfies_its_parent(self):
        # gpt-5.6-sol cited our_posts.606.referenced_video.made_with when the
        # case asked for our_posts.606, and exact matching failed it for being
        # more precise than required.
        assert satisfies(("our_posts.606.referenced_video.made_with",), ("our_posts.606",))

    def test_an_exact_match_still_satisfies(self):
        assert satisfies(("models.kling3_0",), ("models.kling3_0",))

    def test_a_parent_does_not_satisfy_a_specific_requirement(self):
        # Asking for models.kling3_0 and getting `models` back is not evidence
        # that the right entry was read.
        assert not satisfies(("models",), ("models.kling3_0",))

    def test_a_sibling_does_not_satisfy(self):
        assert not satisfies(("models.kling3_0",), ("models.seedance_2_5",))

    def test_a_prefix_that_is_not_a_path_boundary_does_not_satisfy(self):
        # `our_posts.6061` is a different post, not a child of `our_posts.606`.
        assert not satisfies(("our_posts.6061",), ("our_posts.606",))

    def test_nothing_cited_satisfies_nothing(self):
        assert not satisfies((), ("our_posts.606",))
