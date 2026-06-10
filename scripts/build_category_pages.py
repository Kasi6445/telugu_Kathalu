#!/usr/bin/env python3
"""Build static category landing pages for SEO."""
import json, os, re, sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
INDEX_JSON = ROOT / "stories" / "index.json"
SITEMAP = ROOT / "sitemap.xml"

CATEGORIES = [
    ("neeti",        "neethi-kathalu",  "నీతి కథలు",       "Neethi Kathalu",   "#f59e0b"),
    ("panchatantra", "panchatantram",   "పంచతంత్రం కథలు",   "Panchatantram",    "#10b981"),
    ("tenali",       "tenali-rama",     "తెనాలి రామ కథలు",  "Tenali Rama",      "#8b5cf6"),
    ("ramayana",     "ramayanam",       "రామాయణం కథలు",     "Ramayanam",        "#ef4444"),
    ("samethalu",    "samethalu",       "సామెతలు",           "Samethalu",        "#3b82f6"),
    ("janapada",     "janapadam",       "జానపద కథలు",       "Janapadam",        "#ec4899"),
    ("bhagavatam",   "bhagavatam",      "భాగవతం కథలు",      "Bhagavatam",       "#f97316"),
    ("podupu",       "podupu-kathalu",  "పొడుపు కథలు",      "Podupu Kathalu",   "#06b6d4"),
]

INTROS = {
    "neeti":        "నీతి కథలు పిల్లలకు జీవితంలో మంచి విలువలు నేర్పే అద్భుతమైన కథలు. ఈ కథలు పిల్లలలో నిజాయితీ, దయ, సహాయం, ధైర్యం వంటి గుణాలను పెంపొందిస్తాయి. ప్రతి కథలోనూ ఒక విలువైన నీతి దాగి ఉంటుంది.",
    "panchatantra": "పంచతంత్రం కథలు జంతువులు మరియు పక్షుల ద్వారా జీవిత సత్యాలను చెప్పే పురాతన భారతీయ కథలు. ఈ కథలు పిల్లలకు తెలివితేటలు, స్నేహం, విశ్వాసం గురించి నేర్పిస్తాయి.",
    "tenali":       "తెనాలి రామకృష్ణుడు తన తెలివైన సమాధానాలతో అందరినీ ఆశ్చర్యపరిచే గొప్ప విదూషకుడు. తెనాలి రామ కథలు పిల్లలకు తెలివి, హాస్యం మరియు సమస్యలను సులభంగా పరిష్కరించే విధానాన్ని నేర్పిస్తాయి.",
    "ramayana":     "రామాయణం భారతీయ సంస్కృతిలో అత్యంత పవిత్రమైన మహాకావ్యం. శ్రీరాముని జీవితగాథ పిల్లలకు ధర్మం, భక్తి, త్యాగం మరియు మాతాపితరుల పట్ల గౌరవం నేర్పిస్తుంది.",
    "samethalu":    "సామెతలు తెలుగు సంస్కృతిలో తరతరాలుగా వస్తున్న జ్ఞాన వాక్యాలు. ఈ చిన్న వాక్యాలు పెద్ద జీవిత సత్యాలను సరళంగా చెప్తాయి. పిల్లలు సామెతలు నేర్చుకోవడం వల్ల భాష మరియు జ్ఞానం రెండూ పెరుగుతాయి.",
    "janapada":     "జానపద కథలు తెలుగు గ్రామీణ జీవితం నుండి పుట్టిన అమాయకమైన, ఆనందమైన కథలు. ఈ కథలు పిల్లలకు తెలుగు సంస్కృతి, సంప్రదాయాలు మరియు జానపద జీవనశైలిని పరిచయం చేస్తాయి.",
    "bhagavatam":   "భాగవతం శ్రీకృష్ణుని దివ్య లీలలను వర్ణించే పవిత్ర గ్రంథం. బాల కృష్ణుని అద్భుత కథలు పిల్లలకు భక్తి, ప్రేమ మరియు దైవిక శక్తి గురించి నేర్పిస్తాయి.",
    "podupu":       "పొడుపు కథలు పిల్లలకు ఆలోచించే శక్తిని పెంచే తెలివైన చిన్న కథలు. ఈ కథలు పిల్లలలో సమస్యలను పరిష్కరించే నైపుణ్యాన్ని మరియు సృజనాత్మకతను పెంపొందిస్తాయి.",
}

def build_page(code, slug, te_name, en_name, color, stories):
    intro = INTROS[code]
    canonical = f"https://www.telugukathalu.in/{slug}/"
    desc = intro[:150]

    # Schema.org ItemList
    items = ",\n        ".join(
        f'{{"@type":"ListItem","position":{i+1},"url":"https://www.telugukathalu.in/story/{s["slug"]}/","name":{json.dumps(s["title"])}}}'
        for i, s in enumerate(stories)
    )
    schema = f"""{{
      "@context": "https://schema.org",
      "@type": "ItemList",
      "name": "{te_name}",
      "url": "{canonical}",
      "numberOfItems": {len(stories)},
      "itemListElement": [
        {items}
      ]
    }}"""

    # Story cards
    cards = "\n".join(
        f"""      <a class="v-card" href="/story/{s['slug']}/" aria-label="{s['title']}">
        <div class="v-card-img">
          <img loading="lazy" src="{s['thumbnail']}" alt="{s['title']}">
        </div>
        <div class="v-card-body">
          <div class="v-card-title">{s['title']}</div>
          <p class="v-card-moral">💡 {s.get('moral','')}</p>
        </div>
      </a>"""
        for s in stories
    )

    return f"""<!DOCTYPE html>
<html lang="te">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{te_name} - తెలుగు కథలు | Telugu Kathalu</title>
  <meta name="description" content="{desc}">
  <link rel="canonical" href="{canonical}">
  <link rel="stylesheet" href="/static/style.css?v=32">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@400;700&display=swap" rel="stylesheet">
  <script type="application/ld+json">{schema}</script>
</head>
<body>

<header id="main-header">
  <div class="header-top">
    <button id="cat-back-btn" onclick="history.back()" aria-label="అన్ని కథలు">
      <span class="back-arrow">←</span>
      <span id="cat-back-label">అన్నీ</span>
    </button>
    <div class="header-brand" id="header-brand">
      <a href="/" style="text-decoration:none;color:inherit;display:flex;align-items:center;gap:6px">
        <span class="brand-icon">📖</span>
        <span class="brand-name">తెలుగు కథలు</span>
      </a>
    </div>
    <div class="header-icons">
      <a href="/favorites.html" class="header-fav-link" title="నా కథలు">♡</a>
    </div>
  </div>
</header>

<main id="app" style="padding:16px;max-width:1200px;margin:0 auto">

  <section class="category-intro" style="margin-bottom:24px">
    <h1 style="font-size:1.5rem;font-weight:700;color:{color};margin-bottom:8px">{te_name}</h1>
    <p style="font-size:1rem;line-height:1.7;color:var(--text-secondary,#555)">{intro}</p>
    <p style="font-size:0.85rem;color:var(--text-secondary,#888);margin-top:6px">{len(stories)} కథలు అందుబాటులో ఉన్నాయి</p>
  </section>

  <div class="v-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:16px">
{cards}
  </div>

</main>

</body>
</html>"""


def update_sitemap(slugs):
    today = date.today().isoformat()
    if not SITEMAP.exists():
        print("sitemap.xml not found, skipping")
        return
    content = SITEMAP.read_text(encoding="utf-8")
    added = 0
    for slug in slugs:
        url = f"https://www.telugukathalu.in/{slug}/"
        if url in content:
            continue
        entry = f"""  <url>
    <loc>{url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>"""
        content = content.replace("</urlset>", entry + "\n</urlset>")
        added += 1
    SITEMAP.write_text(content, encoding="utf-8")
    print(f"Sitemap: added {added} new URLs")


def main():
    data = json.loads(INDEX_JSON.read_text(encoding="utf-8"))
    stories = data["stories"] if isinstance(data, dict) else data

    by_cat = {}
    for s in stories:
        by_cat.setdefault(s.get("category",""), []).append(s)

    slugs = []
    for code, slug, te_name, en_name, color in CATEGORIES:
        cat_stories = by_cat.get(code, [])
        out_dir = ROOT / slug
        out_dir.mkdir(exist_ok=True)
        html = build_page(code, slug, te_name, en_name, color, cat_stories)
        (out_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"✓ {slug:<20} → {len(cat_stories)} stories → public/{slug}/index.html")
        slugs.append(slug)

    update_sitemap(slugs)
    print("\nDone. 8 category pages generated.")


if __name__ == "__main__":
    main()
