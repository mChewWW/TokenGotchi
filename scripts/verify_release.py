"""Release gate — prove the built executable actually RUNS.

`main.py` must carry an `if __name__ == "__main__"` guard: `tokengotchi.spec`
analyses that file as a script, so without the guard the binary starts,
defines its functions and exits. `console=False` makes that failure silent.

An `exe mtime > source mtime` check proves only that the file was *written*.
It says nothing about whether it works.

This asserts an OBSERVABLE SIDE EFFECT: the app must reach its main loop and
write its state file. A running TokenGotchi cannot leave its save untouched —
it persists every tick.

    python scripts/verify_release.py            # checks dist/TokenGotchi.exe
    python scripts/verify_release.py --source   # checks the source entry point

Exits non-zero and prints why on any failure. Safe to run in CI or a hook.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "TokenGotchi.exe"
STATE = Path.home() / ".tokengotchi" / "state.json"

BOOT_SECONDS = 25.0
SURVIVE_SECONDS = 6.0    # frames must keep rendering, not just start
POLL = 0.4

_fails: list[str] = []
_notes: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    (_notes if ok else _fails).append(
        f"{'PASS' if ok else 'FAIL'}  {label}{('  — ' + detail) if detail else ''}"
    )
    return ok


def _has_main_guard() -> bool:
    """The specific silent-exit defect this gate exists to catch."""
    src = (ROOT / "src" / "tokengotchi" / "main.py").read_text(encoding="utf-8")
    return '__name__ == "__main__"' in src or "__name__ == '__main__'" in src


def _kill_tree(proc: subprocess.Popen, image: str | None = None) -> None:
    """Kill the launched process, its children, and any stragglers.

    Two hazards are handled here:

    1. **Never sweep by image name for an interpreter.** `taskkill /IM
       python.exe /F` would take down this verifier and every other Python
       process on the machine.
    2. **But killing only the PID is not enough for a PyInstaller onefile.**
       The bootloader re-execs, so the real app is a child that outlives the
       PID we launched. Orphaned TokenGotchi.exe processes hold a lock on
       dist/, which makes the NEXT build fail with PermissionError. Sweeping
       by image name is safe here precisely because the image is our own
       binary, never a shared interpreter.
    """
    try:
        proc.kill()
    except Exception:
        pass
    if os.name != "nt":
        return
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                   capture_output=True, check=False)
    if image and image.lower() != "python.exe":
        subprocess.run(["taskkill", "/IM", image, "/F"],
                       capture_output=True, check=False)


def _run_and_watch(cmd: list[str], label: str,
                   image: str | None = None) -> bool:
    """Launch, wait for the state file to be written, then stop it.

    The state file is the observable: the main loop persists on every tick, so
    a touched mtime proves the loop was reached. Nothing else in startup
    writes it.
    """
    backup = None
    if STATE.exists():
        backup = STATE.with_suffix(".json.verify-bak")
        shutil.copy2(STATE, backup)
        before = STATE.stat().st_mtime
    else:
        before = 0.0

    proc = subprocess.Popen(cmd, cwd=str(ROOT),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)
    moved = False
    deadline = time.monotonic() + BOOT_SECONDS
    try:
        while time.monotonic() < deadline:
            time.sleep(POLL)
            if STATE.exists() and STATE.stat().st_mtime > before:
                moved = True
                break
            if proc.poll() is not None:
                break
        # SURVIVAL WINDOW. Reaching the main loop and SURVIVING it are not the
        # same claim, and a gate that stops at the first one is worthless: it
        # would break the moment state.json moved and kill the process right
        # after. State is written before the first frame is drawn, so a build
        # that crashes on frame one still touches state.json and would score a
        # clean 4/4. An AttributeError in the render path with the gate
        # reporting green is the "exe never ran" failure this script exists to
        # prevent, wearing a different hat.
        if moved:
            end = time.monotonic() + SURVIVE_SECONDS
            while time.monotonic() < end:
                time.sleep(POLL)
                if proc.poll() is not None:
                    moved = False      # it started, then died. That is a fail.
                    break
    finally:
        exited_early = proc.poll()
        _kill_tree(proc, image)
        try:
            out = proc.communicate(timeout=5)[0] or ""
        except Exception:
            out = ""
        if backup is not None:
            shutil.copy2(backup, STATE)
            backup.unlink(missing_ok=True)

    if not moved and exited_early is not None:
        tail = "\n      ".join((out or "").strip().splitlines()[-8:])
        return check(False, label,
                     f"process exited (rc={exited_early}) without surviving "
                     f"{SURVIVE_SECONDS}s of the main "
                     f"loop.\n      {tail or '(no output — console=False?)'}")
    return check(moved, label,
                 "" if moved else
                 "ran but never wrote state.json — the main loop was not reached")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="store_true",
                    help="check only the source entry point, skipping the exe")
    args = ap.parse_args()

    print("=" * 68)
    print("RELEASE VERIFICATION")
    print("=" * 68)

    check(_has_main_guard(),
          "main.py has a __main__ guard",
          "" if _has_main_guard() else
          "PyInstaller runs main.py AS A SCRIPT; without the guard the exe "
          "defines functions and exits")

    # ALWAYS run the source entry point as a SCRIPT, even when checking the exe.
    #
    # This is not redundant with the exe check below — it is the only reliable
    # one. `console=False` means a crash inside the frozen app is rendered in a
    # modal message box and THE PROCESS STAYS ALIVE, so a build that dies on
    # frame one still satisfies "wrote state, survived N seconds" and scores
    # green. Running main.py as a script reproduces PyInstaller's entry exactly
    # — module body top to bottom, no import of the package first — and exits
    # non-zero with a traceback instead of hanging on a dialog.
    _run_and_watch([sys.executable, str(ROOT / "src/tokengotchi/main.py")],
                   "source entry point reaches the main loop (script mode)")

    if not args.source:
        if not check(EXE.exists(), "dist/TokenGotchi.exe exists"):
            _report()
            return 1
        newest = max(
            p.stat().st_mtime
            for p in (ROOT / "src").rglob("*.py")
        )
        check(EXE.stat().st_mtime > newest,
              "exe postdates all source",
              "" if EXE.stat().st_mtime > newest else "exe is STALE — rebuild")
        _run_and_watch([str(EXE)],
                       "exe reaches the main loop and writes state",
                       image="TokenGotchi.exe")

    return _report()


def _report() -> int:
    print()
    for line in _notes:
        print("  " + line)
    for line in _fails:
        print("  " + line)
    print()
    if _fails:
        print(f"{len(_fails)} CHECK(S) FAILED — do not ship")
        return 1
    print(f"ALL {len(_notes)} CHECKS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
