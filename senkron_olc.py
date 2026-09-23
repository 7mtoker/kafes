"""Jumpscare ses-goruntu senkronizasyonunu olcer.

Her beklenen korkutma aninin +-0.6 sn cevresinde:
  - goruntu: kareler arasi en buyuk icerik degisimi (ffmpeg scdet/scene skoru)
  - ses: 5 ms'lik pencerelerde en dik gurluk sicramasi
bulunur ve aradaki fark ms cinsinden yazilir. |fark| <= 42 ms (1 kare) ise gecer.

Kullanim: python senkron_olc.py kafes2.mp4 t1 t2 t3 ...   (FFMPEG_BIN ortam degiskeni ya da PATH)
"""
import array
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def arac(ad):
    d = os.environ.get("FFMPEG_BIN")
    if d and (Path(d) / f"{ad}.exe").exists():
        return str(Path(d) / f"{ad}.exe")
    return shutil.which(ad)


def sahne_skorlari(video):
    r = subprocess.run([arac("ffmpeg"), "-hide_banner", "-i", video, "-vf", "scale=160:90,select='gte(scene,0)',metadata=print:key=lavfi.scene_score",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    zaman, skor = [], []
    t = None
    for satir in r.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", satir)
        if m:
            t = float(m.group(1))
        m = re.search(r"lavfi.scene_score=([\d.]+)", satir)
        if m and t is not None:
            zaman.append(t)
            skor.append(float(m.group(1)))
    return zaman, skor


def ses_zarfi(video, pencere=0.005, sr=48000):
    ham = subprocess.run([arac("ffmpeg"), "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True).stdout
    ornek = array.array("h", ham)
    n = int(sr * pencere)
    return [max(abs(x) for x in ornek[i:i + n]) / 32768 for i in range(0, len(ornek) - n, n)], pencere


def main():
    video = sys.argv[1]
    beklenen = [float(x) for x in sys.argv[2:]]
    zaman, skor = sahne_skorlari(video)
    zarf, p = ses_zarfi(video)
    hata = 0
    W = float(os.environ.get("PENCERE", "0.6"))   # bitisik iki olay (belirme ve carpma) icin daralt
    for b in beklenen:
        adaylar = [(s, t) for t, s in zip(zaman, skor) if abs(t - b) <= W]
        if not adaylar:
            print(f"{b:7.3f}s  goruntu olayi bulunamadi"); hata += 1; continue
        _, tg = max(adaylar)
        i0, i1 = int((b - W) / p), int((b + W) / p)
        # ses: kisa gecmise gore en buyuk oransal sicrama
        en, ts = 0, None
        for i in range(max(8, i0), min(len(zarf), i1)):
            once = max(zarf[i - 8:i]) + 1e-4
            oran = zarf[i] / once
            if zarf[i] > 0.12 and oran > en:
                en, ts = oran, i * p
        if ts is None:
            print(f"{b:7.3f}s  ses olayi bulunamadi"); hata += 1; continue
        fark = (ts - tg) * 1000
        durum = "GECTI" if abs(fark) <= 42 else "KALDI"
        if durum == "KALDI":
            hata += 1
        print(f"beklenen {b:7.3f}s | goruntu {tg:7.3f}s | ses {ts:7.3f}s | fark {fark:+6.0f} ms | {durum}")
    print("SONUC:", "tum korkutmalar senkron" if hata == 0 else f"{hata} sorun")
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
