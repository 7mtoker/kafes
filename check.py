"""RADAR kabul testi: maymun-siv farkindalik sayfasi.

Calistir: python check.py   (0 = gecti, 1 = kaldi)
"""
import json
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parent
PAGE = ROOT / "index.html"

REQUIRED_DOIS = [
    "10.1101/cshperspect.a006841",   # Sharp & Hahn 2011
    "10.1126/science.1217550",       # Chahroudi 2012
    "10.1038/nature08200",           # Keele 2009
    "10.1126/science.1126531",       # Keele 2006
    "10.1038/nature07390",           # Worobey 2008
    "10.1126/science.3159089",       # Daniel 1985
    "10.1038/339389a0",              # Hirsch 1989
    "10.1038/17130",                 # Gao 1999
    "10.2305/IUCN.UK.2016-2.RLTS.T15933A17964454.en",  # IUCN 2016
]
AUDIO_EXT = re.compile(r"\.(mp3|wav|ogg|oga|m4a|aac|flac|mid|midi|opus|webm)\b", re.I)
NOTE = re.compile(r"^([A-G])(#|b)?([0-8])$")

failures = []


def fail(msg):
    failures.append(msg)


class Audit(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # (tag, classes, id)
        self.sources = {}        # id -> text
        self.cur_source = None
        self.claims = []         # (data-cite, line)
        self.uncited_numbers = []
        self.scripts = []
        self.json_blocks = {}
        self.cur_script = None
        self.title = ""
        self.in_title = False
        self.ext_refs = []

    def _in(self, pred):
        return any(pred(t, c, i) for t, c, i in self.stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if tag in ("audio", "video", "embed", "object", "iframe"):
            fail(f"yasak etiket <{tag}> (satir {self.getpos()[0]})")
        for key in ("src", "href", "data", "poster"):
            v = a.get(key) or ""
            if AUDIO_EXT.search(v) or v.startswith("data:audio"):
                fail(f"ses dosyasi referansi: {v!r}")
            if key == "src" and v.startswith("http"):
                self.ext_refs.append(v)
        if tag == "link" and (a.get("href") or "").startswith("http"):
            if not a["href"].startswith(("https://fonts.googleapis.com", "https://fonts.gstatic.com")):
                fail(f"izinsiz dis stil: {a['href']}")
        if "claim" in classes:
            self.claims.append((a.get("data-cite"), self.getpos()[0]))
        if tag == "li" and self._in(lambda t, c, i: i == "kaynaklar"):
            self.cur_source = a.get("id")
            self.sources[self.cur_source] = ""
        if tag == "script":
            self.cur_script = {"type": a.get("type", ""), "id": a.get("id"), "src": a.get("src"), "text": ""}
        if tag == "title":
            self.in_title = True
        if tag not in self.VOID:
            self.stack.append((tag, classes, a.get("id")))

    def handle_endtag(self, tag):
        if tag == "script" and self.cur_script is not None:
            s = self.cur_script
            if s["type"] == "application/json":
                self.json_blocks[s["id"]] = s["text"]
            elif not s["src"]:
                self.scripts.append(s["text"])
            self.cur_script = None
        if tag == "title":
            self.in_title = False
        if tag == "li":
            self.cur_source = None
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k][0] == tag:
                del self.stack[k:]
                break

    def handle_data(self, data):
        if self.cur_script is not None:
            self.cur_script["text"] += data
            return
        if self.in_title:
            self.title += data
        if self.cur_source:
            self.sources[self.cur_source] += data
        if self._in(lambda t, c, i: t == "style"):
            return
        # Sayisal iddia denetimi: <main> icindeki her rakam bir .claim icinde
        # (ya da kaynakca / .sayi-muaf icinde) olmali.
        if not self._in(lambda t, c, i: t == "main"):
            return
        if re.search(r"\d", data):
            ok = self._in(lambda t, c, i: "claim" in c or i == "kaynaklar" or "sayi-muaf" in c)
            if not ok:
                self.uncited_numbers.append((self.getpos()[0], data.strip()[:70]))


def beats(seq):
    total = 0.0
    for tok in seq.split():
        name, _, dur = tok.partition(":")
        try:
            d = float(dur)
        except ValueError:
            fail(f"gecersiz sure: {tok}")
            continue
        if name != "R" and not NOTE.match(name):
            fail(f"gecersiz nota: {tok}")
        total += d
    return total


def check_score(raw):
    try:
        score = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"partisyon JSON okunamadi: {e}")
        return
    if len(score) < 3:
        fail(f"en az 3 eser bekleniyordu, {len(score)} var")
    for p in score:
        bpb, bars = p["olcu"], p["olcuSayisi"]
        want = bpb * bars
        mel = beats(p["melodi"])
        if abs(mel - want) > 1e-6:
            fail(f"{p['ad']}: melodi {mel} vurus, beklenen {want}")
        ch = sum(float(c.split(":")[1]) for c in p["akorlar"].split())
        if abs(ch - want) > 1e-6:
            fail(f"{p['ad']}: akorlar {ch} vurus, beklenen {want}")
        for c in p["akorlar"].split():
            for n in c.split(":")[0].split("-"):
                if not NOTE.match(n):
                    fail(f"{p['ad']}: gecersiz akor notasi {n}")


def main():
    if not PAGE.exists():
        print("FAIL index.html yok")
        return 1
    html = PAGE.read_text(encoding="utf-8")
    p = Audit()
    p.feed(html)

    if not p.title.strip():
        fail("<title> yok")
    if html.find("<title>") > 8000:
        fail("<title> ilk 8KB icinde degil")
    for r in p.ext_refs:
        fail(f"dis kaynakli script/medya: {r}")

    # Muzik tamamen sayfada sentezleniyor olmali
    js = "\n".join(p.scripts)
    for needle in ("AudioContext", "createOscillator", "createConvolver"):
        if needle not in js:
            fail(f"sentez kodu eksik: {needle}")
    if re.search(r"fetch\(|XMLHttpRequest|decodeAudioData", js):
        fail("sayfa disaridan ses/veri yukluyor (fetch/XHR/decodeAudioData)")
    if "partisyon" not in p.json_blocks:
        fail("partisyon JSON blogu yok")
    else:
        check_score(p.json_blocks["partisyon"])

    # Kaynaklar
    for doi in REQUIRED_DOIS:
        if doi not in html:
            fail(f"gerekli DOI yok: {doi}")
    for sid, text in p.sources.items():
        if "doi" not in text.lower():
            fail(f"kaynak {sid} DOI icermiyor")
    if not p.claims:
        fail("hic .claim yok")
    for cite, line in p.claims:
        if not cite:
            fail(f"satir {line}: .claim data-cite olmadan")
            continue
        for ref in cite.split(","):
            if ref.strip() not in p.sources:
                fail(f"satir {line}: data-cite {ref!r} kaynakcada yok")
    for line, txt in p.uncited_numbers:
        fail(f"satir {line}: kaynaksiz rakam: {txt!r}")

    # JS sozdizimi
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
        tmp = f.name
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    if r.returncode != 0:
        fail("JS sozdizimi hatasi:\n" + r.stderr[-800:])
    Path(tmp).unlink(missing_ok=True)

    if failures:
        for f_ in failures:
            print("FAIL", f_)
        print(f"{len(failures)} hata")
        return 1
    print(f"OK  {len(p.claims)} iddia, {len(p.sources)} kaynak, partisyon gecerli, JS gecerli")
    return 0


if __name__ == "__main__":
    sys.exit(main())
