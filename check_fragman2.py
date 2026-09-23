"""RADAR kabul testi: KAFES II fragmani ve sayfasi.

Calistir: python check_fragman2.py   (0 = gecti, 1 = kaldi)
ffprobe/ffmpeg PATH'te ya da FFMPEG_BIN ortam degiskeninde olmali.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
failures = []


def fail(m):
    failures.append(m)


def arac(ad):
    d = os.environ.get("FFMPEG_BIN")
    if d and (Path(d) / f"{ad}.exe").exists():
        return str(Path(d) / f"{ad}.exe")
    return shutil.which(ad)


def main():
    video = ROOT / "kafes2.mp4"
    sayfa = ROOT / "fragman2.html"
    kapak = ROOT / "kafes2-kapak.jpg"
    for p in (video, sayfa, kapak):
        if not p.exists():
            fail(f"eksik dosya: {p.name}")
    if failures:
        return bitir()

    boyut = video.stat().st_size / 1e6
    if boyut > 50:
        fail(f"video {boyut:.1f} MB; web icin 50 MB alti olmali")

    ffprobe, ffmpeg = arac("ffprobe"), arac("ffmpeg")
    if not ffprobe or not ffmpeg:
        fail("ffprobe/ffmpeg bulunamadi (FFMPEG_BIN ayarlayin)")
        return bitir()
    info = json.loads(subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
                                     capture_output=True, text=True).stdout)
    sure = float(info["format"]["duration"])
    if not 60 <= sure <= 90:
        fail(f"fragman suresi {sure:.1f} sn; 60-90 olmali")
    v = [s for s in info["streams"] if s["codec_type"] == "video"]
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not v or v[0].get("codec_name") != "h264" or int(v[0]["height"]) < 480:
        fail("video H.264 ve en az 480p olmali")
    if not a:
        fail("ses izi yok")
    else:
        r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(video), "-vn", "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True)
        mx = float(re.search(r"max_volume: (-?[\d.]+) dB", r.stderr).group(1))
        mean = float(re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr).group(1))
        if mx > -0.1:
            fail(f"ses kirpiliyor olabilir (tepe {mx} dB)")
        if mean < -30:
            fail(f"ses cok kisik (ortalama {mean} dB)")

    html = sayfa.read_text(encoding="utf-8")
    for need, why in [('lang="tr"', "Turkce dil etiketi"), ('charset="utf-8"', "UTF-8"), ("kafes2.mp4", "video kaynagi"),
                      ('id="uyari"', "izlemeden once uyari"), ("kurgu", "kurgu aciklamasi"),
                      ("CC BY-SA 4.0", "fragman lisansi"), ("doi.org/10.1038/srep22219", "kamera tuzagi makalesi"),
                      ("Rod Waddington", "fotograf atfi"), ("NaIzletuSi", "hayvanat bahcesi atfi")]:
        if need not in html:
            fail(f"sayfada eksik: {why}")
    if re.search(r"<video[^>]*\bautoplay", html):
        fail("video otomatik oynamamali (uyari once gelmeli)")
    for lisans in ("creativecommons.org/licenses/by/4.0", "creativecommons.org/licenses/by/3.0",
                   "creativecommons.org/licenses/by-sa/2.0"):
        if lisans not in html:
            fail(f"lisans baglantisi yok: {lisans}")
    if 'href="fragman2.html"' not in (ROOT / "index.html").read_text(encoding="utf-8"):
        fail("ana sayfada ikinci fragman baglantisi yok")
    return bitir(sure)


def bitir(sure=None):
    if failures:
        for f in failures:
            print("FAIL", f)
        print(f"{len(failures)} hata")
        return 1
    print(f"OK  KAFES II {sure:.1f} sn, ses ve atiflar gecerli")
    return 0


if __name__ == "__main__":
    sys.exit(main())
