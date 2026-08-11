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

        print("\n[8] frontier shows shape, not content")
        f = eng.frontier()
        check("frontier reports counts only",
              isinstance(f["conclusions_you_could_already_draw"], int))
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
        check("watson does the plumbing but not the thinking",
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
    finally:
        shutil.rmtree(tmp)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    if failed:
        for f_ in failed:
            print(f"  FAILED: {f_}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
