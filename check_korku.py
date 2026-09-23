"""RADAR kabul testi: KAFES korku sitesi ve fragmani.

Calistir: python check_korku.py   (0 = gecti, 1 = kaldi)
"""
import json
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

PAGE = Path(__file__).parent / "index.html"
ASSET_EXT = re.compile(
    r"\.(png|jpe?g|gif|webp|avif|svg|bmp|ico|mp3|wav|ogg|oga|m4a|aac|flac|opus|mid|midi|mp4|webm|mov|"
    r"gltf|glb|obj|fbx|dae|stl|ply|hdr|exr|ktx2?|basis|woff2?|ttf|otf|eot)\b", re.I)
failures = []


def fail(msg):
    failures.append(msg)


class Audit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts, self.json, self.ids, self.cur = [], {}, set(), None
        self.title, self.in_title = "", False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag in ("img", "audio", "video", "source", "picture", "object", "embed", "iframe", "track"):
            fail(f"hazir varlik etiketi <{tag}> (satir {self.getpos()[0]})")
        if tag == "link" and "stylesheet" in (a.get("rel") or ""):
            fail(f"dis stil/yazi tipi: {a.get('href')}")
        for k in ("src", "href", "poster", "data"):
            v = a.get(k) or ""
            if tag == "a" and k == "href":
                continue
            if v and (ASSET_EXT.search(v) or v.startswith("data:") or v.startswith("http")):
                fail(f"dis/hazir kaynak: {tag} {k}={v[:60]}")
        if tag == "script":
            self.cur = {"type": a.get("type", ""), "id": a.get("id"), "src": a.get("src"), "t": ""}
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "script" and self.cur is not None:
            if self.cur["type"] == "application/json":
                self.json[self.cur["id"]] = self.cur["t"]
            elif not self.cur["src"]:
                self.scripts.append(self.cur["t"])
            self.cur = None
        if tag == "title":
            self.in_title = False

    def handle_data(self, d):
        if self.cur is not None:
            self.cur["t"] += d
        elif self.in_title:
            self.title += d


def main():
    html = PAGE.read_text(encoding="utf-8")
    p = Audit()
    p.feed(html)
    if not p.title.strip():
        fail("<title> yok")

    # Hazir varlik yok: CSS url(), @font-face, @import, data: URI
    for pat, why in [(r"url\(", "CSS url()"), (r"@font-face", "@font-face"), (r"@import", "@import"),
                     (r"data:(image|audio|video|font|model|application)", "gomulu data: varlik")]:
        if re.search(pat, html, re.I):
            fail(f"hazir varlik izi: {why}")
    js = "\n".join(p.scripts)
    for pat, why in [(r"\bfetch\(", "fetch"), (r"XMLHttpRequest", "XHR"), (r"decodeAudioData", "decodeAudioData"),
                     (r"new\s+Image\(", "Image()"), (r"texImage2D", "doku yukleme"), (r"import\(", "dinamik import")]:
        if re.search(pat, js):
            fail(f"disaridan varlik yukleme: {why}")

    # Uretim kanitlari
    for needle, why in [("webgl2", "WebGL2 isleyici"), ("AudioContext", "ses sentezi"),
                        ("createOscillator", "osilator"), ("const G = 9.81", "yercekimi sabiti"),
                        ("Math.sin(th)", "sarkac denklemi")]:
        if needle not in js:
            fail(f"eksik: {why} ({needle})")

    # Zaman cizelgesi
    if "zaman" not in p.json:
        fail("zaman JSON blogu yok")
    else:
        z = json.loads(p.json["zaman"])
        sure = z["sure"]
        if not (60 <= sure <= 90):
            fail(f"fragman suresi {sure} sn; 60-90 olmali")
        sah = z["sahneler"]
        if sah[0]["bas"] != 0 or abs(sah[-1]["son"] - sure) > 1e-9:
            fail("sahneler 0'dan baslayip sure'de bitmeli")
        for a, b in zip(sah, sah[1:]):
            if abs(a["son"] - b["bas"]) > 1e-9:
                fail(f"sahne boslugu/cakisma: {a['ad']} -> {b['ad']}")
        tit = sorted(z["titremeler"])
        for a, b in zip(tit, tit[1:]):
            if b - a < 1 / 3:
                fail(f"isik titremesi saniyede 3'ten sik: {a} ve {b}")
        if len(z["korkutmalar"]) < 2:
            fail("en az 2 jumpscare bekleniyordu")

    # Guvenlik ve durustluk
    for i in ("uyari", "izleKorkulu", "izleKorkusuz", "korkutmaAcik"):
        if i not in p.ids:
            fail(f"eksik oge id={i}")
    if "kurgu" not in html.lower():
        fail("kurgu oldugu belirtilmemis")

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
        tmp = f.name
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    if r.returncode != 0:
        fail("JS sozdizimi hatasi:\n" + r.stderr[-800:])
    Path(tmp).unlink(missing_ok=True)

    if failures:
        for x in failures:
            print("FAIL", x)
        print(f"{len(failures)} hata")
        return 1
    print(f"OK  fragman {sure} sn, {len(z['korkutmalar'])} jumpscare, hazir varlik yok, JS gecerli")
    return 0


if __name__ == "__main__":
    sys.exit(main())
