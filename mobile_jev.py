"""mobile-jev: mobilecli drop-in that resolves plain-English element selectors with Jev (typesafe.ai).

Every command is forwarded to mobilecli unchanged. When a tap/longpress target is plain English
("the login button") instead of an @ref or x,y coordinates, the screen's UI tree is ranked by Jev
and the best @ref is substituted, so the agent skips the dump -> read -> pick-ref round-trip.
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

MOBILECLI = os.environ.get("MOBILECLI", "mobilecli")
MODEL = os.environ.get("JEV_MODEL", "jev-latest")
API = os.environ.get("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
CHUNK = 255  # Jev's max options per choice question; bigger screens run a tournament

# "io" subcommand -> positions (in args after the subcommand) that hold a selector
SELECTOR_ARGS = {"tap": (0,), "longpress": (0,)}


def is_natural(arg):
    """True when arg reads as English rather than an @ref or x,y coordinates."""
    a = arg.strip()
    return bool(a) and not a.startswith("-") and not re.fullmatch(r"@e\d+|\d+\s*,\s*\d+", a)


# ---------------------------------------------------------------- Jev


class Jev:
    def predict(self, state, qs):
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            sys.exit("mobile-jev: set TYPESAFE_API_KEY (from https://console.typesafe.ai)")
        req = urllib.request.Request(
            API,
            data=json.dumps({"model": MODEL, "state": state, "questions": qs}).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            sys.exit(f"mobile-jev: Jev API {e.code}: {e.read().decode(errors='replace')}")
        except urllib.error.URLError as e:
            sys.exit(f"mobile-jev: Jev API unreachable: {e.reason}")


def rank(agent, target, elements, state=None, ask=None, fuzzy=True):
    """Pick the element best matching target. elements: [(ref, role, name)]. state/ask override the prompt."""
    labels = {}
    for ref, role, name in elements:
        labels.setdefault(f'{role} "{name}"' if name else role, ref)  # duplicates keep first
    if not labels:
        raise ValueError("no candidate elements on the screen")
    norm = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    want = norm(target)
    names_raw = {label: label.partition('"')[2].lower() for label in labels}
    names = {label: norm(raw) for label, raw in names_raw.items()}
    # lexical fast path, no model; only taken when unambiguous
    words = set(re.findall(r"[a-z0-9]+", target.lower()))
    hits = (
        [label for label, n in names.items() if n == want]
        or [label for label, n in names.items() if fuzzy and len(want) >= 3 and want in n]
        # every word of the name appears in the target: "large pizza" -> radio "Large"
        or [label for label in labels if fuzzy and set(re.findall(r"[a-z0-9]+", names_raw[label])) <= words and names[label]]
    )
    if len(hits) == 1 or (hits and names[hits[0]] == want):
        return {"ref": labels[hits[0]], "label": hits[0], "confidence": 1.0}

    state = state or f"The user wants to: {target}"
    ask = ask or "Which on-screen element should be tapped to accomplish the user's goal?"
    pool = list(labels)
    # tournament: all chunks go in one request, winners race again until one remains
    while len(pool) > 1:
        chunks = [pool[i : i + CHUNK] for i in range(0, len(pool), CHUNK)]
        chunks = [c if len(c) > 1 else c + [c[0] + " "] for c in chunks]  # choice needs 2 options
        qs = {
            f"q{i}": {"type": "choice", "instructions": ask, "criteria": dict.fromkeys(c)}
            for i, c in enumerate(chunks)
        }
        ans = agent.predict(state, qs)["answers"]
        picks = [ans[f"q{i}"] for i in range(len(chunks))]
        pool = [p["choice"].rstrip() for p in picks]
        confidence = picks[0]["confidence"]
    label = pool[0]
    return {"ref": labels[label], "label": label, "confidence": confidence if len(labels) > 1 else 1.0}


# ---------------------------------------------------------------- mobilecli


def flatten(tree):
    """dump ui elements -> [(ref, role, name)], keeping only elements with a name or that are clickable."""
    out = []
    for e in tree:
        clickable = e.get("clickable")
        # identifiers name every layout container, so only use them to label clickable ones
        name = e.get("text") or e.get("label") or (clickable and (e.get("identifier") or "").rpartition("/")[2]) or ""
        if name or clickable:
            out.append((e["ref"].lstrip("@"), e.get("type", "").rpartition(".")[2], name.strip()))
        out += flatten(e.get("children", []))
    return out


def resolve(target, device_flags):
    out = subprocess.run([MOBILECLI, "dump", "ui", *device_flags], capture_output=True, text=True)
    try:
        tree = json.loads(out.stdout)["data"]["elements"]
    except (ValueError, KeyError, TypeError):
        sys.exit(f"mobile-jev: could not dump UI to resolve {target!r}: {out.stderr.strip() or out.stdout.strip()}")
    try:
        res = rank(Jev(), target.strip(), flatten(tree))
    except ValueError as e:
        sys.exit(f"mobile-jev: {e}")
    print(f"jev: {target!r} -> @{res['ref']} {res['label']} ({res['confidence']:.2f})", file=sys.stderr)
    return "@" + res["ref"]


def device_flags(argv):
    """--device X / --device=X anywhere in argv, so dump ui hits the same device."""
    for i, a in enumerate(argv):
        if a.startswith("--device="):
            return [a]
        if a == "--device" and i + 1 < len(argv):
            return argv[i : i + 2]
    return []  # mobilecli falls back to $MOBILECLI_DEVICE


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    i = next((i for i, a in enumerate(argv[:-1]) if a == "io" and argv[i + 1] in SELECTOR_ARGS), None)
    if i is not None:
        sub, args = argv[i + 1], argv[i + 2 :]
        # shortcut: positions count raw args, so flags go after the selector; parse flags properly if that bites
        for p in SELECTOR_ARGS[sub]:
            if p < len(args) and is_natural(args[p]):
                args[p] = resolve(args[p], device_flags(argv))
        argv[i + 2 :] = args
    os.execvp(MOBILECLI, [MOBILECLI, *argv])


if __name__ == "__main__":
    main()
