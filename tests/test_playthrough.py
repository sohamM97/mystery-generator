"""End-to-end playtest of the sealed-case loop.

Runs with plain `python3 tests/test_playthrough.py` — no pytest required, since
the whole point of this repo is that it works from a cold clone.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mystery.schema import Case
from mystery.seal import SealedCase, encrypt, decrypt, new_key
from mystery.engine import Engine, State
from mystery.validate import validate, simulate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFT = os.path.join(ROOT, "examples", "ashgrove.case.json")

passed = []
failed = []


def check(label, condition, detail=""):
    (passed if condition else failed).append(label)
    mark = "ok  " if condition else "FAIL"
    print(f"  {mark} {label}" + (f"  — {detail}" if detail and not condition else ""))


def main():
    case = Case.load(DRAFT)

    print("\n[1] fair-play validation")
    rep = validate(case)
    check("example case validates clean", rep.ok, rep.render())
    check("no warnings either", not rep.warnings, rep.render())

    # An object the player can examine but the room never describes is an
    # object they can only find by naming it at random. The example case is
    # what an authoring LLM copies, so it has to be clean of these — the check
    # above covers that. This one proves the check can still fail.
    import copy as _copy
    blinded = _copy.deepcopy(case)
    examined = next(c for c in blinded.clues if c.source.kind == "examine")
    room = next(l for l in blinded.locations if l.id == examined.source.at)
    room.desc = "A room. Nothing in it but the dark."
    unseen = [i for i in validate(blinded).issues if i.code == "UNSEEN_OBJECT"]
    check("a room that describes none of its objects is flagged", bool(unseen))
    check("...and the flag names the room and the thing",
          any(room.id in i.message and examined.source.ref in i.message
              for i in unseen))
    check("...as an error, so seal refuses it without --force",
          not validate(blinded).ok)

    # The matcher must not dictate prose. A darkroom described as holding "a
    # rack of glass plates" shows the player its top plate, and only the noun
    # the ref ends on may carry that — otherwise `key cabinet` would pass in a
    # room that merely mentions keys.
    from mystery.validate import _describes
    check("a description naming the whole thing shows a part of it",
          _describes("top plate", "red light and a rack of glass plates drying"))
    check("...but a part-word alone is not enough",
          not _describes("key cabinet", "a shadow board, and keys on a nail"))
    check("...and an object nothing describes stays unseen",
          not _describes("safe", "colder than the corridor, nineteen years of paper"))

    print("\n[2] seal round-trips and resists tampering")
    key = new_key()
    blob = encrypt(key, b"the butler did it")
    check("decrypt recovers plaintext", decrypt(key, blob) == b"the butler did it")
    tampered = bytearray(blob)
    tampered[30] ^= 0x01
    try:
        decrypt(key, bytes(tampered))
        check("tampering is detected", False)
    except ValueError:
        check("tampering is detected", True)
    check("ciphertext hides the answer", b"butler" not in blob)

    tmp = tempfile.mkdtemp()
    try:
        sealed = SealedCase(os.path.join(tmp, "ashgrove"))
        sealed.seal(case.to_json())
        check("sealed file is unreadable as text",
              b"mbeki" not in open(sealed.sealed_path, "rb").read().lower())
        reloaded = Case.from_dict(sealed.open_case())
        check("sealed case reloads identically", reloaded.truth.culprit == case.truth.culprit)

        print("\n[3] play: knowledge-gating")
        eng = Engine(case, State(assist="watson"))
        check("starts at the mast", eng.state.at == "mast")
        check("winch house is hidden initially",
              "winchhouse" not in [e["id"] for e in eng.look()["exits"]])
        check("winch house is unreachable initially",
              "winchhouse" not in eng.reachable_locations())
        blocked = eng.travel("winchhouse")
        check("cannot walk into a gated location", not blocked["ok"])

        print("\n[4] play: evidence and premature deduction")
        eng.examine("body")
        eng.examine("wristwatch")
        check("two clues found", len(eng.state.found) == 2)
        d = eng.deduce("r_died_earlier", as_stated="he died before the watch stopped")
        check("under-evidenced conclusion is refused", d["accepted"] is False)
        check("...and recorded as a hunch",
              d.get("recorded") and "r_died_earlier" in eng.state.hunches)
        check("...in the player's own words",
              eng.state.hypotheses[-1]["text"] == "he died before the watch stopped")
        check("...without leaking whether it was right",
              "correct" not in d and "statement" not in d)
        check("...or how close it was", "have" not in d and "need" not in d)

        eng.travel("control")
        eng.examine("duty log")
        d = eng.deduce("r_died_earlier", ["c_watch", "c_snow_under_body", "c_duty_log"])
        check("accepted once the evidence is there", d.get("accepted") is True)

        print("\n[4b] examining what isn't in front of you")
        ex = Engine(case, State(assist="holmes"))
        here = sorted(ex._examinables_at(ex.state.at))
        check("a location knows what can be examined in it", bool(here))
        check("the author's noun is found by a longer one the player used",
              ex.examine(f"the {here[0]}")["flavour"] and
              ex._resolve_ref(f"the {here[0]}", set(here)) == here[0])
        miss = ex.examine("hydraulic press")
        check("a thing that isn't here is reported as absent, not as empty",
              miss["unknown_target"] is True and miss["nothing_here"] is True)
        check("...and says nothing about the thing itself",
              not miss["new_clues"] and "at_hand_elsewhere" not in miss)
        check("...and the guidance forbids narrating it as a finding",
              "never as a finding" in miss["narrator_guidance"])
        # The covered way's description names the doctor's note, visible through
        # the open door, but the clue lives in the mess. Answering that with a
        # bare "nothing here" describes a note with nothing on it.
        elsewhere = None
        for loc in case.locations:
            probe = Engine(case, State(assist="holmes", at=loc.id))
            for other in loc.connects:
                for ref in probe._examinables_at(other):
                    if probe._mentioned_in(ref, loc.desc):
                        elsewhere = probe.examine(ref)
                        break
                if elsewhere:
                    break
            if elsewhere:
                break
        if elsewhere is not None:
            check("a thing this room names but cannot reach says where it is",
                  bool(elsewhere.get("at_hand_elsewhere")) and not elsewhere["new_clues"])
        else:
            check("a thing this room names but cannot reach says where it is",
                  False, "Ashgrove has lost its visible-but-out-of-reach pair")
        gated_ref = next((c.source.ref for c in case.clues
                          if c.source.kind == "examine" and c.gates), "")
        if gated_ref:
            g = Engine(case, State(assist="holmes"))
            g.state.at = next(c.source.at for c in case.clues
                              if c.source.kind == "examine" and c.gates)
            res = g.examine(gated_ref)
            check("a gated object still reads as present, not absent",
                  "unknown_target" not in res)

        print("\n[5] play: a conclusion opens new ground")
        eng.travel("mast")
        eng.examine("stairway")
        eng.examine("rail")
        eng.search()
        d = eng.deduce("r_not_a_fall")
        check("r_not_a_fall accepted", d.get("accepted") is True)
        check("...and it opened the winch house", "Winch House" in d.get("opened", []))
        check("winch house now an exit",
              "winchhouse" in [e["id"] for e in eng.look()["exits"]])

        print("\n[6] play: prerequisites are enforced")
        eng2 = Engine(case, State(assist="holmes"))
        d = eng2.deduce("r_culprit_mbeki", as_stated="mbeki killed him")
        check("cannot leap straight to the culprit", d["accepted"] is False)

        # The oracle test: a true-but-unproved statement, a true-but-premature
        # one, and a statement the case has never heard of must be
        # indistinguishable from outside — otherwise stating theories and
        # reading the replies is a way to find out which ones are true.
        eng3 = Engine(case, State(assist="holmes"))
        eng3.examine("body")
        unproved = eng3.deduce("r_died_earlier", as_stated="he died earlier than they say")
        premature = eng3.deduce("r_culprit_mbeki", as_stated="mbeki did it")
        unmatched = eng3.deduce("", as_stated="the lighthouse keeper is a foreign agent")
        check("an unproved, a premature and an unmatched claim look identical",
              unproved == premature == unmatched)
        check("...and all three are filed in the player's own words",
              [h["text"] for h in eng3.state.hypotheses]
              == ["he died earlier than they say", "mbeki did it",
                  "the lighthouse keeper is a foreign agent"])
        check("...with nothing marking which ones the case can back",
              all(set(h) == {"text", "turn", "at"} for h in eng3.journal()["suspicions"]))
        check("an unmatched claim is not recorded as a hunch",
              eng3.state.hunches == ["r_died_earlier", "r_culprit_mbeki"])
        check("the same claim twice does not double up",
              eng3.deduce("", as_stated="mbeki did it") and
              len(eng3.state.hypotheses) == 3)
        check("an unknown conclusion id is still an error",
              eng3.deduce("r_nonexistent", as_stated="x")["ok"] is False)

        print("\n[7] play: liars stay consistent, and are debunkable")
        lie = case.clue("c_mbeki_account")
        check("the lie is flagged internally", lie.reliability == "false")
        check("...and something reachable debunks it", bool(lie.debunked_by))
        view = eng._clue_view(lie)
        check("reliability is marked never-reveal", "NEVER_REVEAL" in view)
        check("...and absent from the player-facing fields",
              "false" not in (view["headline"] + view["detail"]).lower())

        # `ask` keys clues by an exact topic string the narrator never gets to
        # see, and a miss costs a turn. Wording it a little differently has to
        # reach the same subject. The authored topics are pulled out of the
        # case rather than written down here — this file is read by people who
        # may still play Ashgrove.
        print("\n[7b] asking about a subject, worded differently")
        askable = [c for c in case.clues if c.source.kind == "ask"]
        # Prefer a subject of several words if the case has one; a one-word
        # subject exercises everything here except the reordering.
        sample = max(askable, key=lambda c: len(c.source.topic.split()))
        who, subject = sample.source.ref, sample.source.topic

        def asks(engine, worded):
            return engine.ask(who, worded).get("new_clues", [])

        check("the author's own wording still works",
              bool(asks(Engine(case, State()), subject)))
        check("...and so does a leading 'the'",
              bool(asks(Engine(case, State()), "the " + subject)))
        check("...and a question wrapped around it",
              bool(asks(Engine(case, State()), f"what do you know about {subject}?")))
        if len(subject.split()) > 1:
            check("...and the words in another order",
                  bool(asks(Engine(case, State()), " ".join(reversed(subject.split())))))
        check("a subject nobody wrote finds nothing",
              not asks(Engine(case, State()), "the price of fish in Belgium"))
        check("one subject asked two ways is one question, not two",
              Engine(case, State()) and
              (e2 := Engine(case, State())) is not None and
              (asks(e2, subject), asks(e2, "the " + subject)) and
              len(e2.state.asked) == 1)

        # A tie must not be broken by guessing. Spending the player's turn on
        # whichever subject happened to sort first is the bug this replaced,
        # so a phrase that fits two subjects equally must reach neither.
        ambiguous = Engine(case, State())
        # The two subjects must be the same length in words, or the longer one
        # simply matches more of the muddle and wins on count — which is the
        # resolver working, not the tie this checks.
        mine = [c.source.topic for c in askable if c.source.ref == who]
        pair = next(([a, b] for i, a in enumerate(mine) for b in mine[i + 1:]
                     if len(a.split()) == len(b.split())), [])
        if len(pair) == 2:
            muddled = " ".join(pair)  # every word of both subjects, at once
            check("wording that fits two subjects equally resolves to neither",
                  ambiguous._resolve_topic(who, muddled) == "")
            check("...and asking it finds nothing rather than the wrong thing",
                  not asks(Engine(case, State()), muddled))

        print("\n[8] frontier shows shape, not content")
        f = eng.frontier()
        check("frontier reports counts only",
              isinstance(f["conclusions_you_could_already_draw"], int))
        # holmes promises that nothing is inferred for the player. A count of
        # conclusions that would land right now is an inference: it says the
        # evidence in hand is already enough, and stopping the search to think
        # is the decision holmes exists to leave with them.
        holmes_f = Engine(case, State(assist="holmes")).frontier()
        check("holmes is not told whether a conclusion is ready",
              "conclusions_you_could_already_draw" not in holmes_f)
        check("...and the shape of the case is still there to take stock of",
              {"places_with_loose_ends", "people_with_more_to_say",
               "clues_found", "clues_total"} <= set(holmes_f))
        check("...and the narrator is told not to guess at what it withheld",
              "holmes" in holmes_f["narrator_guidance"])
        for level in ("watson", "lestrade"):
            check(f"{level} still gets the count",
                  isinstance(Engine(case, State(assist=level))
                             .frontier()["conclusions_you_could_already_draw"], int))
        # Naming who still has something to say is the point — it's the ship
        # log. What must never appear is a clue id or a conclusion, which is
        # what would turn "take stock" into "here is the answer".
        blob_text = str(f).lower()
        check("frontier leaks no clue ids",
              not any(c.id.lower() in blob_text for c in case.clues))
        check("frontier leaks no conclusions",
              not any(r.id.lower() in blob_text or r.statement.lower() in blob_text
                      for r in case.revelations))
        check("frontier singles nobody out",
              len(f["people_with_more_to_say"]) > 3)

        print("\n[9] a wrong accusation the case anticipated")
        eng3 = Engine(case, State(assist="lestrade"))
        v = eng3.accuse("corrigan")
        check("wrong culprit rejected", v["correct_culprit"] is False)
        check("...but recognised as an anticipated theory", v.get("your_theory_was_anticipated"))
        check("...and refuted with a specific clue", len(v.get("refuted_by", [])) > 0)
        check("...without revealing the real culprit", "truth" not in v)

        print("\n[10] a lucky guess grades worse than a proved case")
        lucky = Engine(case, State(assist="lestrade"))
        v_lucky = lucky.accuse("mbeki")
        check("guessing right is still 'right'", v_lucky["correct_culprit"] is True)
        check("...but graded a lucky guess", v_lucky["grade"] == "lucky guess",
              str(v_lucky["grade"]))

        thorough = Engine(case, State(assist="lestrade"))
        found, held = simulate(case)
        thorough.state.found = list(found)
        thorough.state.held = list(held)
        v_good = thorough.accuse("mbeki", motive="the forged arrester record and Doyle's death",
                                 method="hoisted up the mast on the winch")
        check("a fully worked case is airtight", v_good["grade"] == "airtight", str(v_good["grade"]))
        check("...and only then is the truth released", "truth" in v_good)
        check("motive overlap is reported as a ratio, not a ruling",
              isinstance(v_good["motive_overlap"], float) and v_good["motive_overlap"] > 0)
        check("...and a motive said in the player's own words isn't a miss",
              thorough.accuse("mbeki", motive="he was covering up a death he caused"
                              )["motive_overlap"] == 0.0)
        check("...while a shared stopword alone scores nothing",
              thorough.accuse("mbeki", motive="because that would have been")
              ["motive_overlap"] == 0.0)
        check("an unstated motive scores nothing",
              thorough.accuse("mbeki")["motive_overlap"] == 0.0)

        print("\n[11] assist levels differ")
        holmes = Engine(case, State(assist="holmes"))
        holmes.examine("body"); holmes.examine("wristwatch"); holmes.travel("control")
        holmes.examine("duty log")
        check("holmes infers nothing for you", holmes.state.held == [])
        lestrade = Engine(case, State(assist="lestrade"))
        lestrade.examine("body"); lestrade.examine("wristwatch"); lestrade.travel("control")
        lestrade.examine("duty log")
        check("lestrade draws the conclusion for you", "r_died_earlier" in lestrade.state.held)
        watson = Engine(case, State(assist="watson"))
        watson.travel("control"); watson.travel("office")
        watson.examine("photograph")
        watson.travel("mess"); watson.ask("ivy", "safe")
        check("watson draws the connecting steps but not the chain",
              "r_safe_combination" in watson.state.held)
        check("...and leaves critical conclusions alone",
              "r_died_earlier" not in watson.state.held)

        print("\n[12] the perfect detective can finish the case")
        check("every clue is reachable", len(found) == len(case.clues),
              f"{len(found)}/{len(case.clues)}")
        check("every critical conclusion is reachable",
              all(r.id in held for r in case.revelations if r.critical))

        print("\n[13] the player's notebook")
        nb = Engine(case, State(assist="watson"))
        nb.travel("control")
        r_note = nb.note("the duty log is in two different hands")
        check("a note is stored verbatim",
              r_note["note"]["text"] == "the duty log is in two different hands")
        check("...stamped with where it was written",
              r_note["note"]["at"] == case.location("control").name)
        nb.note("mbeki is lying about the winch")
        nb.note("the butler did it")
        check("notes accumulate in order",
              [n["text"] for n in nb.notebook()["notes"]][-1] == "the butler did it")
        check("notes ride along in the journal", len(nb.journal()["notes"]) == 3)
        check("a wrong note is kept, not corrected",
              any(n["text"] == "the butler did it" for n in nb.notebook()["notes"]))
        check("notes never become evidence", nb.state.found == [] and nb.state.held == [])
        check("...and never become conclusions", nb.state.hunches == [])
        check("notes are numbered 1-based for the player",
              [n["n"] for n in nb.notebook()["notes"]] == [1, 2, 3])

        print("\n[13b] striking and amending")
        r_strike = nb.strike(3)
        check("a struck note reports ok", r_strike["ok"] and r_strike["note"]["struck"])
        check("a struck note stays on the page",
              [n["text"] for n in nb.notebook()["notes"]][2] == "the butler did it")
        check("...still crossed out when read back",
              nb.notebook()["notes"][2]["struck"] is True)
        check("...and keeps its number", nb.notebook()["notes"][2]["n"] == 3)
        check("striking is not deleting", len(nb.state.notes) == 3)
        check("striking twice is harmless",
              nb.strike(3)["ok"] and nb.strike(3)["already_struck"])
        check("striking a note that isn't there fails quietly",
              nb.strike(99)["ok"] is False and nb.strike(0)["ok"] is False)
        check("...and changes nothing", len(nb.state.notes) == 3)

        r_amend = nb.amend(2, "mbeki's winch story checks out after all")
        check("an amendment writes a new line",
              r_amend["ok"] and r_amend["note"]["n"] == 4)
        check("...that records what it replaced", r_amend["note"]["replaces"] == 2)
        check("...and strikes the old one", nb.notebook()["notes"][1]["struck"] is True)
        check("the replaced wording survives verbatim",
              nb.notebook()["notes"][1]["text"] == "mbeki is lying about the winch")
        check("amending a note that isn't there fails",
              nb.amend(99, "nope")["ok"] is False)
        check("...without writing the replacement", len(nb.state.notes) == 4)
        check("struck notes ride along in the journal",
              sum(1 for n in nb.journal()["notes"] if n.get("struck")) == 2)
        check("striking still never becomes evidence",
              nb.state.found == [] and nb.state.held == [] and nb.state.hunches == [])
        r_unstrike = nb.unstrike(2)
        check("a struck note can be unstruck",
              r_unstrike["ok"] and r_unstrike["was_struck"])
        check("...and reads back with no rule through it",
              "struck" not in nb.notebook()["notes"][1])
        check("...leaving no scar", "struck_turn" not in nb.state.notes[1])
        check("unstriking a note that was never struck is harmless",
              nb.unstrike(1)["ok"] and nb.unstrike(1)["was_struck"] is False)

        r_rewrite = nb.rewrite(3, "the butler has an alibi")
        check("a rewrite replaces the wording in place",
              r_rewrite["ok"] and nb.notebook()["notes"][2]["text"]
              == "the butler has an alibi")
        check("...keeping the note's number", r_rewrite["note"]["n"] == 3)
        check("...without adding a line", len(nb._notes_view()) == 4)
        check("...keeping the old wording in the record",
              nb.state.notes[2]["revisions"][0]["text"] == "the butler did it")
        check("...but off the page",
              "revisions" not in nb.notebook()["notes"][2])

        r_torn = nb.tear_out(4)
        check("a torn-out line leaves the page", r_torn["ok"]
              and [n["n"] for n in nb.notebook()["notes"]] == [1, 2, 3])
        check("...but survives in state as a tombstone",
              nb.state.notes[3]["torn"] is True and len(nb.state.notes) == 4)
        check("...and its number is never reused",
              nb.note("a fresh line")["note"]["n"] == 5)
        check("a torn-out line can no longer be addressed",
              nb.strike(4)["ok"] is False and nb.rewrite(4, "z")["ok"] is False)
        check("torn-out lines are gone from the journal too",
              all(n["n"] != 4 for n in nb.journal()["notes"]))
        check("count is what's on the page, not what's in state",
              nb.notebook()["count"] == 4 and len(nb.state.notes) == 5)
        check("editing still never becomes evidence",
              nb.state.found == [] and nb.state.held == [] and nb.state.hunches == [])
        check("every notebook op speaks with one voice",
              len({nb.note("x")["narrator_guidance"],
                   nb.strike(1)["narrator_guidance"],
                   nb.unstrike(1)["narrator_guidance"],
                   nb.rewrite(1, "y")["narrator_guidance"],
                   nb.tear_out(1)["narrator_guidance"],
                   nb.amend(2, "z")["narrator_guidance"]}) == 1)
        check("...including when the number doesn't exist",
              nb.strike(99)["narrator_guidance"] == nb.rewrite(99, "q")["narrator_guidance"])

        print("\n[13c] the case board")
        # Play far enough to hold a conclusion, then look at the wiring.
        bd = Engine(case, State(assist="watson"))
        for c in case.clues:
            bd.state.found.append(c.id)
        bd.auto_infer()
        check("the board shows what the player has concluded",
              len(bd.board()["established"]) == len(bd.state.held) > 0)
        first = bd.board()["established"][0]
        check("...with the evidence under each conclusion", bool(first["because"]))
        check("...and only evidence the player actually holds",
              all(c["id"] in bd.state.found
                  for e in bd.board()["established"] for c in e["because"]))
        check("the board never looks forward",
              all(k not in bd.board() for k in ("ripe", "next", "available")))
        held_ids = {e["id"] for e in bd.board()["established"]}
        check("the board shows no conclusion the player hasn't drawn",
              held_ids <= set(bd.state.held))
        check("conclusions the assist level drew are marked as the game's",
              all(e["drawn_by"] == "the game" for e in bd.board()["established"]))
        check("...in the journal too",
              all(e["drawn_by"] == "the game" for e in bd.journal()["established"]))
        drew = Engine(case, State(assist="holmes"))
        drew.state.found.extend(c.id for c in case.clues)
        first_rev = next(r for r in case.revelations if not r.requires)
        drew.deduce(first_rev.id)
        check("a conclusion the player reasoned to is marked as theirs",
              drew.board()["established"][0]["drawn_by"] == "you")
        loose = bd.board()["unattached_clues"]
        check("loose ends are named but never explained",
              all(set(c) == {"id", "headline"} for c in loose))

        holmes_bd = Engine(case, State(assist="holmes"))
        holmes_bd.state.found.extend(c.id for c in case.clues)
        holmes_bd.state.held.append(bd.state.held[0])
        holmes_bd.deduce("", as_stated="somebody moved the body")
        hb = holmes_bd.board()
        check("holmes gets the conclusions and none of the wiring",
              "because" not in hb["established"][0])
        check("...but keeps their own unproved statements, which leak nothing",
              [h["text"] for h in hb["suspicions"]] == ["somebody moved the body"])
        lestrade_bd = Engine(case, State(assist="lestrade"))
        lestrade_bd.state.found.extend(c.id for c in case.clues)
        lestrade_bd.auto_infer()
        check("lestrade is told which conclusions rest on the bare minimum",
              all("resting_on_minimum" in e
                  for e in lestrade_bd.board()["established"]))
        check("the board is read-only",
              (before := (list(bd.state.found), list(bd.state.held), bd.state.turns))
              and bd.board() and (list(bd.state.found), list(bd.state.held),
                                  bd.state.turns) == before)

        # A notebook that vanishes between sessions is not a notebook.
        st_path = os.path.join(tmp, "notes-state.json")
        nb.state.save(st_path)
        check("notes survive a save/load round trip",
              [n["text"] for n in State.load(st_path).notes]
              == [n["text"] for n in nb.state.notes])
        check("...and so do the lines ruled through them",
              [n.get("struck", False) for n in State.load(st_path).notes]
              == [n.get("struck", False) for n in nb.state.notes])
        # State files written before `notes` existed must still load.
        import json as _json
        legacy = _json.load(open(st_path))
        del legacy["notes"]
        legacy_path = os.path.join(tmp, "legacy-state.json")
        _json.dump(legacy, open(legacy_path, "w"))
        check("a pre-notes state file still loads", State.load(legacy_path).notes == [])

        # [13d] The casebook rearranges what the player already has. Its job is
        # to add nothing — so what it must never contain is the whole test.
        print("\n[13d] the casebook")
        from mystery import casebook

        cb_eng = Engine(case, State(assist="watson"))
        cb_eng.state.found.extend(c.id for c in case.clues[:4])
        cb_eng.auto_infer()
        cb_eng.note("a line in my own hand")
        cb_eng.deduce("", as_stated="the boatman is lying about the tide")
        built = casebook.pages(cb_eng)
        everything = "\n".join("\n".join(body) for _, _, body in built)

        check("every page is built", [n for n, _, _ in built] == casebook.PAGE_NAMES)
        check("no page leaks the narrator's guidance",
              "narrator_guidance" not in everything
              and "NEVER_REVEAL" not in everything
              and "Do NOT" not in everything)
        check("no page leaks a clue's reliability",
              not any(c.hidden_note and c.hidden_note in everything for c in case.clues))
        check("the player's own note reaches the notebook page",
              "a line in my own hand" in casebook.render(cb_eng, "notebook"))
        check("...and their unproved statement is on the conclusions page",
              "the boatman is lying about the tide"
              in casebook.render(cb_eng, "conclusions"))
        check("a clue they have not found is on no page",
              not any(c.headline in everything for c in case.clues
                      if c.id not in cb_eng.state.found))
        check("an unknown page name renders nothing",
              casebook.render(cb_eng, "the culprit") == "")

        # Opening the casebook is reading, not acting.
        was = (list(cb_eng.state.found), cb_eng.state.turns, len(cb_eng.state.notes))
        casebook.pages(cb_eng)
        check("reading the casebook spends no turn and changes nothing",
              (list(cb_eng.state.found), cb_eng.state.turns,
               len(cb_eng.state.notes)) == was)

        # holmes withholds two things elsewhere; the casebook is built on those
        # same views, so it must withhold them here without being told twice.
        holmes_cb = Engine(case, State(assist="holmes"))
        holmes_cb.state.found.extend(c.id for c in case.clues)
        holmes_cb.deduce("", as_stated="somebody moved the body")
        holmes_text = "\n".join("\n".join(b) for _, _, b in casebook.pages(holmes_cb))
        check("holmes sees no count of conclusions already carried",
              "would already carry" not in holmes_text)

        # An author who fills in age and gender gets them; one who doesn't
        # gets no empty brackets where they would have been.
        bare = casebook.render(Engine(case, State()), "cast")
        check("a cast with no ages recorded shows no empty ones",
              "()" not in bare and ", )" not in bare)

        import copy
        filled = copy.deepcopy(case)
        filled.cast[0].age, filled.cast[0].gender = "forty-one", "woman"
        sheet = Engine(filled, State()).cast_sheet()["cast"]
        check("an author who records age and gender gets both",
              sheet[0]["age"] == "forty-one" and sheet[0]["gender"] == "woman")
        check("...and a character left blank carries neither key",
              "age" not in sheet[1] and "gender" not in sheet[1])
        check("...and the filled-in ones reach the cast page",
              "(forty-one, woman)" in casebook.render(Engine(filled, State()), "cast"))
        # Sealing writes the case back out through to_dict.
        check("the new fields survive a round trip through the schema",
              Case.from_dict(_json.loads(filled.to_json())).cast[0].age == "forty-one")

        # [14] Development must not write into a case someone is playing.
        # A session working on `deduce` reached for a played case as its test
        # target and left a suspicion in it that the player never said. Two
        # answers: `scratch` gives development a copy to aim at, and every
        # write records the state it replaced so `undo` can take it back.
        print("\n[14] scratch copies and the state history")
        import io
        import contextlib
        from mystery import cli

        def run(*argv):
            """Call the CLI in-process and return its parsed JSON output."""
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli.main(list(argv))
            out = buf.getvalue().strip()
            return code, (_json.loads(out) if out.startswith(("{", "[")) else out)

        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            live = os.path.join(tmp, "ashgrove")
            run("look", "--case", live)  # a case only gets a state once it is played
            live_before = open(os.path.join(live, "state.json")).read()
            _, made = run("scratch", "--case", live)
            copy = made["case"]
            check("scratch names a copy under scratch/",
                  made["ok"] and copy.startswith("scratch" + os.sep))
            check("...that is a playable case in its own right",
                  SealedCase(copy).exists())
            _, again = run("scratch", "--case", live)
            check("...and a second copy does not overwrite the first",
                  again["case"] != copy)

            run("deduce", "--case", copy, "--as-stated", "the butler did it")
            run("note", "--case", copy, "a test note")
            check("writing to the copy leaves the original alone",
                  open(os.path.join(live, "state.json")).read() == live_before)
            check("...and the original grows no history of its own",
                  not os.path.exists(os.path.join(live, "state.history.jsonl")))

            after = State.load(os.path.join(copy, "state.json"))
            check("the copy took both writes",
                  len(after.hypotheses) == 1 and len(after.notes) == 1)
            hist = open(os.path.join(copy, "state.history.jsonl")).read().splitlines()
            check("each write recorded the state it replaced", len(hist) == 2)
            check("...along with the command that made it",
                  [_json.loads(h)["cmd"][0] for h in hist] == ["deduce", "note"])

            _, undone = run("undo", "--case", copy)
            check("undo names what it took back", undone["undid"][0] == "note")
            check("...and removes the note", not State.load(
                os.path.join(copy, "state.json")).notes)
            run("undo", "--case", copy)
            check("undoing every write restores the state the copy started with",
                  open(os.path.join(copy, "state.json")).read() == live_before)
            code, empty = run("undo", "--case", copy)
            check("undo with nothing behind it fails plainly",
                  code == 1 and not empty["ok"])

            # Everything a narrator can see, it will eventually offer the
            # player, and a player who can undo can take back a spent hint.
            help_text = cli.build_parser().format_help()
            check("neither tool appears in --help",
                  "undo" not in help_text and "scratch" not in help_text)
            check("...and no placeholder is left where they were",
                  "SUPPRESS" not in help_text)

            # A hint is paid for once, in the grade. Charging a turn as well
            # would price it twice, and the skills promise the player it costs
            # no turn before they decide whether to spend one.
            print("\n[15] a hint is charged to the grade, not the clock")
            _, h_copy = run("scratch", "--case", live)
            hc = h_copy["case"]
            before = State.load(os.path.join(hc, "state.json"))
            run("hint", "--case", hc)
            after = State.load(os.path.join(hc, "state.json"))
            check("a hint spends no turn", after.turns == before.turns)
            check("...and does not count against the run of empty turns",
                  after.turns_since_progress == before.turns_since_progress)
            check("...but is recorded", after.hints_used == before.hints_used + 1)
            _, verdict = run("accuse", "--case", hc, "mbeki")
            check("...and is read out with the verdict", verdict["hints_used"] == 1)

            # Taking stock stays free too, and for the same reason: it holds
            # nothing the player has not already earned.
            free_before = State.load(os.path.join(hc, "state.json")).turns
            for cmd in ("journal", "board", "cast", "frontier", "casebook", "status"):
                run(cmd, "--case", hc)
            check("taking stock spends no turn",
                  State.load(os.path.join(hc, "state.json")).turns == free_before)
        finally:
            os.chdir(cwd)
    finally:
        shutil.rmtree(tmp)

    # The narrator is the only thing that remembers a conversation, and a
    # conversation can be trimmed. Without this, a player returning to a case
    # pays a turn to be told what their detective is looking straight at.
    print("\n[16] a room remembers what it has already shown")
    sh = Engine(case, State(assist="watson"))
    check("a room that has not been looked at shows nothing",
          sh.journal()["within_reach"] == [])
    check("...and says so, rather than passing for a room holding nothing",
          sh.journal()["looked_around"] is False)
    shown = sh.look()["examinable"]
    check("looking records what the room named",
          sh.state.shown[sh.state.at] == sorted(shown))
    check("...and the journal reads it back for free",
          sh.journal()["within_reach"] == sorted(shown))
    check("...marked as looked at", sh.journal()["looked_around"] is True)

    # The covered way's trap: looked at, and genuinely holding nothing. It
    # must not read the same as a room nobody has walked into.
    bare = Engine(case, State(assist="watson"))
    bare.state.shown[bare.state.at] = []
    check("a room looked at and holding nothing is told apart from an unvisited one",
          bare.journal()["within_reach"] == [] and bare.journal()["looked_around"] is True)
    turns_before = sh.state.turns
    sh.journal()
    check("...without spending a turn", sh.state.turns == turns_before)

    sh.travel("control")
    check("arriving somewhere records that room too",
          sh.state.shown["control"] == sorted(sh.look()["examinable"]))
    check("...and the journal follows the detective",
          sh.journal()["within_reach"] == sh.state.shown["control"])
    check("the room they left is remembered separately",
          "mast" in sh.state.shown and sh.state.shown["mast"] != sh.state.shown["control"])

    # Only what was displayed is remembered. The office holds a safe gated on
    # r_safe_combination: the room does not name it until the player works the
    # combination out, so the free read-back must not hand it to them early.
    gate = Engine(case, State(assist="watson"))
    gate.travel("control")
    gate.travel("office")
    check("a thing still gated when they looked is not in the read-back",
          "safe" not in gate.journal()["within_reach"])
    gate.examine("photograph")
    gate.travel("mess")
    gate.ask("ivy", "safe")
    check("...until the conclusion that opens it is drawn",
          "r_safe_combination" in gate.state.held)
    before = list(gate.state.shown["office"])
    gate.travel("office")
    check("...and then a fresh look adds it", "safe" in gate.journal()["within_reach"])
    check("...without dropping what the room named the first time",
          all(ref in gate.state.shown["office"] for ref in before))

    # Cases played before this field existed have a state file without it.
    old_path = os.path.join(tempfile.mkdtemp(), "state.json")
    with open(old_path, "w", encoding="utf-8") as fh:
        fh.write('{"assist": "watson", "at": "mast", "turns": 4}')
    old = State.load(old_path)
    check("a state file written without the field still loads", old.shown == {})
    check("...and reads back as nothing shown yet",
          Engine(case, old).journal()["within_reach"] == [])

    # The verdict rules on two things: right person, and provable. Neither can
    # show that a case was solved with four conclusions handed over and three
    # hints spent. This is that record, and it is counts only — never a score.
    # The engine tracks nobody's position, so the same person answers in every
    # room their testimony lives in. The field must not invite the narrator to
    # claim they are standing there.
    print("\n[17] who you can speak to is reach, not position")
    reach = Engine(case, State(assist="watson"))
    check("a look says who can be spoken to, not who is here",
          "people_here" not in reach.look())

    # Arthur Bell answers in the mess and in the covered way, so this is real
    # in Ashgrove — built here anyway so the check survives Bell being moved.
    twice = _copy.deepcopy(case)
    spoken = next(c for c in twice.clues if c.source.kind == "ask")
    second = _copy.deepcopy(spoken)
    second.id = spoken.id + "_elsewhere"
    second.source.at = next(l.id for l in twice.locations if l.id != spoken.source.at)
    second.supports = []
    twice.clues.append(second)
    two_rooms = Engine(twice, State(assist="watson"))
    where = set()
    for loc in twice.locations:
        two_rooms.state.at = loc.id
        if any(p["id"] == spoken.source.ref
               for p in two_rooms.look()["people_you_can_speak_to"]):
            where.add(loc.id)
    check("...and one person answering in two rooms appears in both",
          where == {spoken.source.at, second.source.at})
    g = reach.look()["narrator_guidance"]
    check("look carries guidance, like every other engine response", bool(g))
    check("...telling the narrator to write reach rather than a fixed spot",
          "not who is standing where" in g)
    check("...and forbidding searchable from becoming a nudge",
          "Never mention `searchable`" in g)

    print("\n[18] the verdict says how they got there")
    lest = Engine(case, State(assist="lestrade"))
    lest.examine("body"); lest.examine("wristwatch"); lest.travel("control")
    lest.examine("duty log")
    got = lest.accuse("mbeki")["how_you_got_here"]
    check("the read-out names the assist level", got["assist"] == "lestrade")
    check("...and counts what the game drew for them", got["conclusions_given"] > 0)
    check("...apart from what they reasoned to",
          got["conclusions_reasoned"] + got["conclusions_given"] == len(lest.state.held))

    cold = Engine(case, State(assist="holmes"))
    cold.examine("body"); cold.examine("wristwatch"); cold.travel("control")
    cold.examine("duty log")
    cold_got = cold.accuse("mbeki")["how_you_got_here"]
    check("holmes hands over nothing, and the read-out shows it",
          cold_got["conclusions_given"] == 0)

    check("a hint spent is carried into the verdict", cold.hint() and
          cold.accuse("mbeki")["how_you_got_here"]["hints_used"] == 1)
    check("earlier accusations are counted, this one excluded",
          cold.accuse("mbeki")["how_you_got_here"]["earlier_accusations"] == 2)

    check("evidence no conclusion rests on is counted",
          cold_got["clues_never_used"] == len(cold.board()["unattached_clues"]))
    check("...and conclusions stated but never carried",
          cold_got["never_established"] == 0)
    cold.deduce("r_culprit_mbeki", as_stated="mbeki did it")
    check("...which a hunch that never landed increases",
          cold.accuse("mbeki")["how_you_got_here"]["never_established"] == 1)

    # It is a record, not a verdict of its own. Nothing in it may read as
    # praise or reproach, and it must not reveal which ideas were right.
    guidance = cold.accuse("mbeki")["narrator_guidance"]
    check("the guidance forbids reading it as a second score",
          "not a second score" in guidance and "never be delivered as praise" in guidance)
    check("...and forbids saying what the unused evidence would have proved",
          "saying what it would have proved" in guidance)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    if failed:
        for f_ in failed:
            print(f"  FAILED: {f_}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
