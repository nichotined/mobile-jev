import mobile_jev
from mobile_jev import device_flags, flatten, is_natural, rank


class FakeAgent:  # picks the option containing "submit", else the first
    def predict(self, state, qs):
        pick = lambda c: next((o for o in c if "submit" in o), list(c)[0])
        return {"answers": {k: {"choice": pick(q["criteria"]), "confidence": 0.9} for k, q in qs.items()}}


def test_is_natural():
    for sel in ["@e1", "@e42", "100,200", "100, 200", "--device", ""]:
        assert not is_natural(sel), sel
    for nl in ["the login button", "Sign in (beta)", "button", "post a story"]:
        assert is_natural(nl), nl


def test_rank():
    els = [(f"e{i}", "TextView", f"story {i}") for i in range(600)]
    els += [("e700", "Button", "login"), ("e701", "Button", "submit")]
    assert rank(FakeAgent(), "log in", els)["ref"] == "e700"  # lexical fast path
    assert rank(FakeAgent(), "post a story", els)["ref"] == "e701"  # tournament across 3 chunks
    radios = [("e1", "RadioButton", " Medium"), ("e2", "RadioButton", " Large")]
    assert rank(FakeAgent(), "large pizza", radios)["ref"] == "e2"  # word-subset fast path


def test_flatten():
    tree = [{"ref": "@e1", "type": "android.widget.FrameLayout", "text": "", "children": [
        {"ref": "@e2", "type": "android.widget.TextView", "text": "2:14", "identifier": "com.android.systemui:id/clock"},
        {"ref": "@e3", "type": "android.view.ViewGroup", "text": "", "clickable": True},
        {"ref": "@e4", "type": "android.widget.ImageView", "label": "Settings"},
        {"ref": "@e5", "type": "android.widget.ImageView", "identifier": "com.app:id/search_icon", "clickable": True},
        {"ref": "@e6", "type": "android.widget.LinearLayout", "identifier": "com.app:id/container"},
    ]}]
    assert flatten(tree) == [
        ("e2", "TextView", "2:14"), ("e3", "ViewGroup", ""), ("e4", "ImageView", "Settings"), ("e5", "ImageView", "search_icon"),
    ]


def test_main_rewrites_selector():
    calls = []
    mobile_jev.resolve = lambda target, flags: calls.append((target, flags)) or "@e9"
    mobile_jev.os.execvp = lambda prog, argv: calls.append(argv)
    mobile_jev.main(["io", "tap", "log in", "--device", "emu"])
    mobile_jev.main(["io", "tap", "100,200"])
    assert calls == [("log in", ["--device", "emu"]), ["mobilecli", "io", "tap", "@e9", "--device", "emu"], ["mobilecli", "io", "tap", "100,200"]]
    assert device_flags(["--device=x", "io"]) == ["--device=x"]


if __name__ == "__main__":
    test_is_natural(); test_rank(); test_flatten(); test_main_rewrites_selector(); print("ok")
