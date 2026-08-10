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
        d = eng.deduce("r_died_earlier")
        check("under-evidenced conclusion is refused", d["accepted"] is False)
        check("...and recorded as a hunch", d.get("hunch") and "r_died_earlier" in eng.state.hunches)
        check("...without leaking whether it was right", "correct" not in d and "statement" not in d)

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
        d = eng2.deduce("r_culprit_mbeki")
        check("cannot leap straight to the culprit", d["ok"] is False and d.get("premature"))

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
        check("motive matching works", v_good["motive_matched"] is True)

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
