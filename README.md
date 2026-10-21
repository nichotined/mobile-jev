# mobile-jev

**[mobilecli](https://github.com/mobile-next/mobilecli), but tap targets can be plain English, resolved by [Jev](https://typesafe.ai) in a single typed decision.**

`mobile-jev` accepts every mobilecli command and passes it through unchanged. When a `tap`/`longpress` target is English (`io tap "log in"`) instead of an `@ref` or `x,y`, the screen's UI tree is sent to Jev, TypeSafe's typed-decision model, which picks the matching element. The agent skips the dump → read → pick-ref round-trip, and there's no LLM call or prompt to parse.

Forked from [laya-browser](https://github.com/Benny93/laya-browser), which does the same for agent-browser with a local Laya model.

## Install

Requires Python 3.11+, [mobilecli](https://github.com/mobile-next/mobilecli) on `PATH`, and a TypeSafe API key from [console.typesafe.ai](https://console.typesafe.ai).

```bash
uv tool install git+https://github.com/nichotined/mobile-jev   # or: git clone … && uv tool install --editable .
export TYPESAFE_API_KEY=...
```

No other dependencies: Jev is called with the standard library.

## Usage

```bash
export MOBILECLI_DEVICE=Medium_Phone_API_35       # or pass --device after the selector
mobile-jev io tap "log in"                        # jev: 'log in' -> @e12 Button "Log in" (1.00)
mobile-jev io longpress "the first message" --device emulator-5554
mobile-jev io tap @e5                             # refs and coordinates pass straight through
mobile-jev io tap 100,200
mobile-jev io fill "hello"                        # every other command is plain mobilecli
```

Each resolved pick is logged to stderr with its confidence, so an agent can fall back to an `@ref` when it's low.

**Resolution:**
1. Run `mobilecli dump ui` and keep elements that have text, a label, or are clickable.
2. Try an unambiguous text match with no model: "log in" → `login`, "large pizza" → radio `Large`.
3. Otherwise ask Jev one `choice` question over the elements (up to 255 options per question; bigger screens run a tournament in one request).
4. Exec `mobilecli io tap @eN …` with the picked ref.

**Environment:**
- `TYPESAFE_API_KEY`: required for step 3.
- `JEV_MODEL`: Jev model (default `jev-latest`).
- `TYPESAFE_API_URL`: API endpoint (default `https://api.typesafe.ai/v1/systemone`).
- `MOBILECLI`: path to the mobilecli binary.

## Limitations

- Only `io tap` and `io longpress` resolve English. To fill a field, tap it first, then `io fill`.
- Put flags after the selector (`io tap "x" --device …`).
- Any target that isn't `@eN` or `x,y` counts as English.
- Step 3 is a paid network call to Jev; exact text matches skip it.
- Jev's confidence isn't a guarantee, and vague targets on crowded screens can miss.

## Development

```bash
python test_mobile_jev.py   # stdlib-only check, no device or API key needed
```

## License

Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Jev is by TypeSafe; mobilecli is by mobile-next. Neither is affiliated with this project.
