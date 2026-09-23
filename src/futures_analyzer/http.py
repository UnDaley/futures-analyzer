"""Dış kaynaklardan metin indirmek için ortak yardımcı.

Siteler User-Agent başlığına farklı tepki veriyor (Eylül 2026'da denendi):
- FRED: tarayıcı gibi görünen veya özel isim içeren başlıkları reddediyor
- Federal Reserve: Python'un varsayılan başlığını reddediyor
Hepsinin kabul ettiği ortak başlık curl'ün başlığı olduğu için onu kullanıyoruz.
"""

import urllib.request

USER_AGENT = "curl/8.5.0"


def get_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")
