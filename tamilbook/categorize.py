"""Guess a book's category from its words.

Deliberately simple and transparent: weighted keyword *prefixes* (Tamil is
agglutinative, so "கோயில்" also matches "கோயிலுக்கு", "கோயிலில்"...).
Volunteers can improve the lists without any ML knowledge. The result is a
suggestion - always overridable with --category.
"""
from __future__ import annotations

from collections import Counter

CATEGORIES: dict[str, dict] = {
    "fiction": {
        "ta": "நாவல் / புனைவு",
        "words": ["நாவல்", "அத்தியாயம்", "சொன்னாள்", "சொன்னான்", "என்றாள்",
                  "என்றான்", "கேட்டாள்", "கேட்டான்", "சிரித்தாள்", "சிரித்தான்",
                  "பார்த்தாள்", "பார்த்தான்", "நினைத்தாள்", "நினைத்தான்"],
    },
    "short-stories": {
        "ta": "சிறுகதைகள்",
        "words": ["சிறுகதை", "கதைகள்", "தொகுப்பு"],
    },
    "poetry": {
        "ta": "கவிதை",
        "words": ["கவிதை", "பாடல்", "பாட்டு", "பாக்கள்", "வெண்பா", "விருத்தம்"],
    },
    "classical": {
        "ta": "இலக்கியம் / இலக்கணம்",
        "words": ["இலக்கணம்", "தொல்காப்பி", "குறள்", "செய்யுள்", "சங்க",
                  "புறநானூ", "அகநானூ", "உரையாசிரியர்", "பதவுரை", "விளக்கவுரை",
                  "நன்னூல்", "எழுத்ததிகாரம்", "சொல்லதிகாரம்"],
    },
    "history": {
        "ta": "வரலாறு",
        "words": ["வரலாறு", "வரலாற்று", "மன்னன்", "மன்னர்", "ஆட்சி", "போர்",
                  "கல்வெட்டு", "நூற்றாண்டு", "சோழ", "பாண்டிய", "பல்லவ", "சேர",
                  "பேரரசு", "படையெடுப்பு"],
    },
    "biography": {
        "ta": "வாழ்க்கை வரலாறு",
        "words": ["வாழ்க்கை வரலாறு", "பிறந்தார்", "மறைந்தார்", "இளமைப்",
                  "இளமையில்", "தந்தையார்", "தாயார்", "காலமானார்"],
    },
    "religion": {
        "ta": "ஆன்மீகம் / சமயம்",
        "words": ["இறைவன்", "கடவுள்", "சிவன்", "சிவபெருமான்", "திருமால்",
                  "முருக", "கோயில்", "பக்தி", "அருள்", "வழிபாடு", "தேவாரம்",
                  "ஆழ்வார்", "நாயன்மார்", "அல்லா", "இயேசு", "புத்தர்", "சமண",
                  "பிரார்த்தனை", "தியானம்"],
    },
    "science": {
        "ta": "அறிவியல்",
        "words": ["அறிவியல்", "அணு", "ஆற்றல்", "வேதியியல்", "இயற்பியல்",
                  "உயிரியல்", "கணிதம்", "சமன்பாடு", "பரிசோதனை", "விஞ்ஞான"],
    },
    "society": {
        "ta": "சமூகம் / அரசியல்",
        "words": ["அரசியல்", "சமூக", "கட்சி", "சுதந்திர", "உரிமை",
                  "பொருளாதார", "தேர்தல்", "சாதி", "பெண்ணுரிமை", "விடுதலை"],
    },
    "children": {
        "ta": "சிறுவர்",
        "words": ["சிறுவர்", "குழந்தைகள்", "குட்டி", "முயல்", "நரி", "காக்கை",
                  "யானை", "குரங்கு", "தாத்தா", "பாட்டி"],
    },
    "health": {
        "ta": "உடல்நலம் / மருத்துவம்",
        "words": ["மருத்துவ", "நோய்", "சித்த", "மூலிகை", "சிகிச்சை",
                  "உடல்நல", "ஆயுர்வேத", "மருந்து"],
    },
    "cooking": {
        "ta": "சமையல்",
        "words": ["சமையல்", "தேக்கரண்டி", "வதக்க", "பரிமாற", "மிளகாய்",
                  "எண்ணெய்", "கடுகு", "தாளித்"],
    },
}


def categorize(text: str, verse_hint: bool = False, top: int = 3) -> dict:
    """Return {"category", "category_ta", "scores": [(cat, score), ...]}."""
    words = Counter(text.split())
    total = max(sum(words.values()), 1)
    scores: dict[str, float] = {}
    for cat, info in CATEGORIES.items():
        hits = 0
        for kw in info["words"]:
            if " " in kw:
                hits += text.count(kw) * 3
            else:
                hits += sum(n for w, n in words.items() if w.startswith(kw))
        scores[cat] = hits * 1000 / total   # hits per 1000 words
    if verse_hint:
        scores["poetry"] = scores.get("poetry", 0) + 5
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best = ranked[0][0] if ranked and ranked[0][1] > 0.5 else "general"
    return {
        "category": best,
        "category_ta": CATEGORIES.get(best, {}).get("ta", "பொது"),
        "scores": [(c, round(s, 2)) for c, s in ranked[:top]],
    }
