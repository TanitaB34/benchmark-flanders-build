"""
Digitale benchmark Flanders Build - Verstraete.team
---------------------------------------------------
Haalt wekelijks publieke publicaties op over alle bedrijven in bedrijven.csv:
  - nieuwsartikels via de openbare RSS-feeds van Google Nieuws en Bing Nieuws
  - nieuwe pagina's op de eigen website (via RSS-feed en/of sitemap)
  - extra feeds die je zelf toevoegt (bv. YouTube-kanaal, blog)
  - LinkedIn-cijfers die je manueel invult in linkedin_manueel.csv

Resultaat: data/publicaties.json (archief) en docs/data.js (voor het dashboard).
Je hoeft dit script niet zelf te starten: GitHub doet dat elke maandag.
"""

import csv
import datetime as dt
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
ARCHIEF = DATA_DIR / "publicaties.json"
SITEMAP_STATUS = DATA_DIR / "website_status.json"


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 VerstraeteBenchmark/1.0"
)
BEWAARTERMIJN_DAGEN = 400          # oudere publicaties worden opgeruimd
TERUGBLIK_NORMAAL = 10             # dagen terugkijken bij een wekelijkse run
TERUGBLIK_EERSTE_RUN = 120         # bij de allereerste run iets meer historiek
MAX_NIEUWE_PAGINAS = 20            # per website per run
MAX_ARTIKELS_PER_BEDRIJF = 40      # max. aantal artikels dat per bedrijf per run geopend wordt
PAUZE = 1.2                        # seconden tussen verzoeken (beleefd blijven)

THEMAS = {
    "BIM & digitaal": [
        "bim", "digital twin", "digitale tweeling", "digitaal", "digitale", "digitalis",
        "data", "software", "4d", "5d", " ai ", "artifici", "puntenwolk", "scan",
        "drone", "platform", "numérique", "digital",
    ],
    "Duurzaamheid": [
        "duurza", "circula", "circulair", "co2", "klimaat", "energie", "warmtepomp",
        "hernieuwbaar", "biodivers", "houtbouw", "biobased", "durable", "sustainab",
        "emissie", "fossielvrij", "zonnepan",
    ],
    "Projecten & werven": [
        "project", "werf", "oplevering", "opgeleverd", "eerste steen", "start der werken",
        "nieuwbouw", "renovatie", "restauratie", "appartement", "woningen", "school",
        "ziekenhuis", "kantoor", "chantier", "bouwt", "realiseert", "aanbesteding",
        "gegund", "contract",
    ],
    "HR & talent": [
        "vacature", "job", "aanwerv", "medewerker", "talent", "stage", "opleiding",
        "collega", "welzijn", "werken bij", "emploi", "recrut", "hiring", "team",
        "gezocht", "projectleider", "werfleider", "calculator", "ploegbaas",
    ],
    "Bedrijf & financieel": [
        "overname", "neemt over", "fusie", "omzet", "winst", "resultaat", "investeert",
        "investering", "groei", "ceo", "directie", "benoem", "faillis", "kapitaal",
        "acquisition", "acquires", "jaarverslag", "aandeelhouder",
    ],
    "Innovatie & prefab": [
        "innovat", "prefab", "modulair", "modulaire", "robot", "3d-print", "3d print",
        "industrieel bouwen", "startup", "start-up", "pilot", "proefproject", "onderzoek",
    ],
    "Events & awards": [
        "award", "prijs", "winnaar", "wint", "beurs", "event", "seminarie", "congres",
        "flanders build", "genomineerd", "laureaat", "webinar", "opendeur",
    ],
}

sessie = requests.Session()
sessie.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "nl-BE,nl;q=0.9,en;q=0.7"})


# ---------------------------------------------------------------- hulpfuncties

def log(tekst):
    print(tekst, flush=True)


def haal_op(url, timeout=20):
    """Haalt een URL op met 2 pogingen. Geeft None terug bij een fout."""
    for poging in range(2):
        try:
            r = sessie.get(url, timeout=timeout, allow_redirects=True)
            time.sleep(PAUZE)
            if r.status_code == 200:
                return r
            if r.status_code in (404, 410, 403):
                return None
        except requests.RequestException:
            time.sleep(2)
    return None


def maak_id(tekst):
    return hashlib.sha1(tekst.encode("utf-8")).hexdigest()[:16]


def schoon(tekst, maxlen=None):
    tekst = html.unescape(re.sub(r"<[^>]+>", " ", tekst or ""))
    tekst = re.sub(r"\s+", " ", tekst).strip()
    if maxlen and len(tekst) > maxlen:
        tekst = tekst[: maxlen - 1].rsplit(" ", 1)[0] + "…"
    return tekst


def normaliseer_titel(titel):
    return re.sub(r"[^a-z0-9]+", "", titel.lower())[:80]


def naar_datum(struct):
    if not struct:
        return None
    try:
        return dt.date(struct.tm_year, struct.tm_mon, struct.tm_mday)
    except (ValueError, AttributeError):
        return None


def iso_week(datum):
    j, w, _ = datum.isocalendar()
    return f"{j}-W{w:02d}"


def bepaal_themas(tekst):
    t = f" {tekst.lower()} "
    scores = {}
    for thema, woorden in THEMAS.items():
        n = sum(1 for w in woorden if w in t)
        if n:
            scores[thema] = n
    if not scores:
        return ["Overige"]
    return [k for k, _ in sorted(scores.items(), key=lambda kv: -kv[1])][:3]


def bouw_query(bedrijf):
    namen = [n.strip() for n in bedrijf["zoeknamen"].split("|") if n.strip()]
    context = [c.strip() for c in bedrijf["context"].split("|") if c.strip()]
    q = " OR ".join(f'"{n}"' for n in namen)
    if context:
        # In Google/Bing bindt OR sterker dan AND: (namen) EN (een van de contextwoorden)
        q += " " + " OR ".join(f'"{c}"' if " " in c else c for c in context)
    return q


def naam_in_tekst(bedrijf, tekst):
    t = tekst.lower()
    namen = [n.strip().lower() for n in bedrijf["zoeknamen"].split("|") if n.strip()]
    return any(n in t for n in namen)


# Woorden die erop wijzen dat een artikel over een bedrijf of de bouwsector gaat.
BEDRIJFSWOORDEN = re.compile(
    r"bouw|aannem|werf|werven|project|renov|restaur|architect|studiebureau|ingenieur|engineering|"
    r"infra|vastgoed|ontwikkelaar|steenfabriek|baksteen|gevelsteen|fabriek|onderaannem|"
    r"investe|winst|omzet|verlies|overname|neemt over|fusie|dividend|ondernemingsrechtbank|"
    r"personeel|medewerker|vacature|uitstoot|duurza|circulai|offshore|windpark|haven|bagger|"
    r"order|contract|aanbesteding|gegund|oplevering|woning|appartement|woonzorg|ziekenhuis|"
    r"kantoor|campus|schoolsite|technisch advies|digitaal|software|modulai|prefab|robot|"
    r"veiligheid|federatie|sector|voka|\bnv\b|\bbv\b|\bceo\b|\bco2\b|\bco₂\b|\bbim\b|\bai\b",
    re.I)
# Typische ruis: sport, overlijdens, verenigingsleven, leeftijden van personen.
RUIS = re.compile(
    r"overleden|\b\d{2,3} jaar\b|\(\d{1,2}\)|voetbal|padel|wielren|bmx|topduif|duivensport|"
    r"fotoclub|\bzege\b|\bwint\b|\bk[fv]c\b|\bfc\b|gt world",
    re.I)


def is_bedrijfsnieuws(bedrijf, titel, samenvatting, medium):
    """Houdt een persartikel enkel als het echt over het bedrijf gaat:
    1. de bedrijfsnaam staat in de titel of samenvatting (of het is een publicatie van het bedrijf zelf),
    2. er staat een woord in dat op bedrijfs- of bouwnieuws wijst (of een woord uit de kolom context),
    3. het is geen sport-, overlijdens- of verenigingsbericht."""
    if medium:  # Google Nieuws plakt de naam van het medium achter de samenvatting
        samenvatting = samenvatting.replace(medium, " ")
    tekst = f"{titel} {samenvatting}"
    eigen_medium = naam_in_tekst(bedrijf, medium or "")
    if not (naam_in_tekst(bedrijf, tekst) or eigen_medium):
        return False
    if RUIS.search(titel):
        return False
    if eigen_medium or heeft_bedrijfscontext(bedrijf, tekst):
        return True
    # Naam staat in de titel als bedrijfsnaam (niet als voor- of achternaam van een persoon)
    namen = [n.strip() for n in bedrijf["zoeknamen"].split("|") if n.strip()]
    for naam in namen:
        for m in re.finditer(r"(?<![\w-])" + re.escape(naam) + r"(?![\w-])", titel, re.I):
            if not lijkt_persoonsnaam(titel, m.start(), m.end()):
                return True
    return False


def heeft_bedrijfscontext(bedrijf, tekst):
    context = [c.strip().lower() for c in bedrijf.get("context", "").split("|") if c.strip()]
    t = tekst.lower()
    return any(c in t for c in context) or bool(BEDRIJFSWOORDEN.search(tekst))


# ---------------------------------------------------------------- vermelding in de artikeltekst

def google_link_naar_bron(url):
    """Google Nieuws geeft omleidingslinks (news.google.com/rss/articles/...).
    Zet zo'n link om naar het echte artikel. Geeft None terug als dat niet lukt."""
    if "news.google.com" not in url:
        return url
    m = re.search(r"/articles/([^?/#]+)", url)
    if not m:
        return None
    gid = m.group(1)
    try:
        r = sessie.get(f"https://news.google.com/rss/articles/{gid}", timeout=20)
        time.sleep(PAUZE)
        sig = re.search(r'data-n-a-sg="([^"]+)"', r.text)
        ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
        if not (sig and ts):
            return None
        verzoek = [[["Fbv4je",
                     f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
                     f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts.group(1)},"{sig.group(1)}"]',
                     None, "generic"]]]
        r = sessie.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                        data={"f.req": json.dumps(verzoek)},
                        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                        timeout=20)
        time.sleep(PAUZE)
        deel = r.text.split("\n\n", 1)[1]
        echte = json.loads(json.loads(deel)[0][2])[1]
        return echte if echte.startswith("http") else None
    except Exception:
        return None


def artikeltekst(html_tekst):
    """Haalt de leesbare tekst van een artikel uit de HTML, zonder menu's, zijbalken en voettekst."""
    stukken = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html_tekst, re.I | re.S):
        for body in re.findall(r'"articleBody"\s*:\s*"((?:[^"\\]|\\.)*)"', m.group(1)):
            try:
                stukken.append(json.loads(f'"{body}"'))
            except ValueError:
                pass
    h = re.sub(r"<(script|style|noscript|nav|header|footer|aside|form)\b.*?</\1>", " ", html_tekst, flags=re.I | re.S)
    artikels = re.findall(r"<article\b.*?</article>", h, re.I | re.S)
    if artikels:
        h = " ".join(artikels)
    else:
        b = re.search(r"<body\b.*?</body>", h, re.I | re.S)
        h = b.group(0) if b else h
    stukken.append(html.unescape(re.sub(r"<[^>]+>", " ", h)))
    return re.sub(r"\s+", " ", " ".join(stukken)).strip()


TOEGELATEN_VOOR = {"bouwbedrijf", "bouwgroep", "bouwfirma", "aannemer", "groep", "group", "firma", "bureau",
                   "studiebureau", "architectenbureau", "de", "het", "een", "en", "bij", "door", "voor", "van",
                   "met", "ook", "of", "aan", "dat", "die", "volgens", "zoals", "nv", "bv", "maar", "dus", "toen",
                   "nu", "zo", "daarom", "daarnaast", "bovendien", "intussen", "gisteren", "vandaag", "hier",
                   "daar", "waar", "wie", "wat", "omdat", "als", "want", "hoewel", "sinds", "na", "tijdens", "in",
                   "op", "uit", "om", "over", "onder", "tussen", "naast", "dankzij", "ceo", "aannemers", "partner",
                   "bouwpartner", "klant", "opdrachtgever", "ontwikkelaar", "architect", "studiebureau's", "ook"}
TOEGELATEN_NA = {"nv", "bv", "bvba", "group", "groep", "construct", "bouw", "architects", "architecten",
                 "engineering", "infra", "unitec", "steenfabrieken", "living", "automation", "ai", "en", "uit",
                 "in", "is", "heeft", "wordt", "werd", "de", "het", "van", "voor", "bouwt", "realiseert", "en"}


def lijkt_persoonsnaam(tekst, start, einde):
    """True als de naam er staat als achternaam of voornaam van een persoon (bv. 'Jasper Vandersanden')."""
    voor = re.search(r"([A-Za-zÀ-ÿ'-]+)\s+$", tekst[max(0, start - 40):start])
    na = re.match(r"\s+([A-Za-zÀ-ÿ'-]+)", tekst[einde:einde + 40])
    if voor:
        w = voor.group(1)
        plaatsnaam = re.search(r"(se|sche)$", w.lower())  # Veurnse, Gentse, Limburgse ...
        if w[:1].isupper() and w.lower() not in TOEGELATEN_VOOR and not plaatsnaam:
            return True
    if na:
        w = na.group(1)
        if w[:1].isupper() and w.lower() not in TOEGELATEN_NA:
            return True
    return False


def vermelding_in_artikel(bedrijf, url):
    """Opent het artikel en zoekt of het bedrijf erin vermeld wordt in een zakelijke context.
    Geeft het tekstfragment rond de vermelding terug, of None."""
    echte = google_link_naar_bron(url)
    if not echte:
        return None, None
    r = haal_op(echte, timeout=20)
    if not r or "html" not in r.headers.get("Content-Type", "html"):
        return None, echte
    tekst = artikeltekst(r.text)
    namen = [n.strip() for n in bedrijf["zoeknamen"].split("|") if n.strip()]
    for naam in namen:
        for m in re.finditer(r"(?<![\w-])" + re.escape(naam) + r"(?![\w-])", tekst, re.I):
            if lijkt_persoonsnaam(tekst, m.start(), m.end()):
                continue
            venster = tekst[max(0, m.start() - 250):m.end() + 250]
            if RUIS.search(venster) or not heeft_bedrijfscontext(bedrijf, venster):
                continue
            fragment = tekst[max(0, m.start() - 110):m.end() + 130]
            return "…" + fragment.strip() + "…", echte
    return None, echte


# ---------------------------------------------------------------- bronnen

def google_nieuws(bedrijf, dagen):
    q = bouw_query(bedrijf) + f" when:{dagen}d"
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
           + "&hl=nl&gl=BE&ceid=BE:nl")
    r = haal_op(url)
    if not r:
        return None
    resultaten = []
    for e in feedparser.parse(r.content).entries:
        titel = schoon(e.get("title", ""))
        medium = ""
        if e.get("source") and e.source.get("title"):
            medium = e.source.title
            if titel.endswith(" - " + medium):
                titel = titel[: -(len(medium) + 3)]
        resultaten.append({
            "titel": titel,
            "url": e.get("link", ""),
            "datum": naar_datum(e.get("published_parsed")),
            "medium": medium or "Google Nieuws",
            "samenvatting": schoon(e.get("summary", ""), 240),
            "bron": "Google Nieuws",
        })
    return resultaten


def bing_nieuws(bedrijf):
    url = ("https://www.bing.com/news/search?format=rss&setlang=nl-BE&cc=BE&count=50&q="
           + urllib.parse.quote(bouw_query(bedrijf)))
    r = haal_op(url)
    if not r:
        return None
    resultaten = []
    for e in feedparser.parse(r.content).entries:
        link = e.get("link", "")
        echte = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("url")
        if echte:
            link = echte[0]
        medium = e.get("news_source", "")  # Bing levert <News:Source>
        resultaten.append({
            "titel": schoon(e.get("title", "")),
            "url": link,
            "datum": naar_datum(e.get("published_parsed")),
            "medium": medium or urllib.parse.urlparse(link).netloc.replace("www.", ""),
            "samenvatting": schoon(e.get("summary", ""), 240),
            "bron": "Bing Nieuws",
        })
    return resultaten


def lees_feed(url, bron, domein_label):
    r = haal_op(url)
    if not r:
        return None
    feed = feedparser.parse(r.content)
    if not feed.entries:
        return None
    return [{
        "titel": schoon(e.get("title", "")) or e.get("link", ""),
        "url": e.get("link", ""),
        "datum": naar_datum(e.get("published_parsed") or e.get("updated_parsed")),
        "medium": domein_label,
        "samenvatting": schoon(e.get("summary", ""), 240),
        "bron": bron,
    } for e in feed.entries]


def volg_nieuwspagina(url, status_archief):
    """Voor nieuwspagina's zonder RSS: meldt nieuwe links onder die pagina (bv. /nieuws/...).
    De eerste keer wordt enkel een nulmeting gemaakt."""
    r = haal_op(url)
    if not r or "html" not in r.headers.get("Content-Type", "html"):
        return None
    basis = urllib.parse.urlparse(r.url)
    pad = basis.path.rstrip("/")
    links = {}
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', r.text, re.I | re.S):
        link = urllib.parse.urljoin(r.url, html.unescape(m.group(1))).split("?")[0].rstrip("/")
        lp = urllib.parse.urlparse(link)
        if lp.netloc != basis.netloc or SKIP_EXT.search(link):
            continue
        if not (lp.path.startswith(pad + "/") and len(lp.path) > len(pad) + 1):
            continue
        tekst = schoon(m.group(2), 160)
        if len(tekst) > len(links.get(link, "")):
            links[link] = tekst
    if not links:
        return []
    sleutel = "pagina:" + url
    gekend = set(status_archief.get(sleutel, []))
    status_archief[sleutel] = sorted(gekend | {maak_id(l) for l in links})
    if not gekend:
        return []  # nulmeting
    domein = basis.netloc.replace("www.", "")
    return [{
        "titel": t if len(t) > 8 else pagina_titel(l), "url": l, "datum": dt.date.today(),
        "medium": domein, "samenvatting": "", "bron": "Nieuwspagina",
    } for l, t in links.items() if maak_id(l) not in gekend][:MAX_NIEUWE_PAGINAS]


def zoek_website_feeds(website, homepage_html):
    feeds = []
    for m in re.finditer(r"<link[^>]+>", homepage_html, re.I):
        tag = m.group(0)
        if re.search(r'type=["\']application/(rss|atom)\+xml', tag, re.I):
            href = re.search(r'href=["\']([^"\']+)', tag, re.I)
            if href:
                link = urllib.parse.urljoin(website, html.unescape(href.group(1)))
                if "comments" not in link:
                    feeds.append(link)
    if not feeds and "wp-content" in homepage_html:
        feeds.append(urllib.parse.urljoin(website, "/feed/"))
    return list(dict.fromkeys(feeds))[:3]


SKIP_EXT = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|mp4|doc|docx|xls|xlsx)$", re.I)
SKIP_PAD = re.compile(r"/(tag|tags|category|categorie|author|auteur|page|wp-json|feed|cart|checkout)/", re.I)


def lees_sitemap(website, robots_tekst):
    kandidaten = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_tekst or "")
    kandidaten += [urllib.parse.urljoin(website, p) for p in
                   ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")]
    for start in dict.fromkeys(kandidaten):
        urls = {}
        wachtrij, bezocht = [start], 0
        while wachtrij and bezocht < 15:
            sm = wachtrij.pop(0)
            bezocht += 1
            r = haal_op(sm)
            if not r:
                continue
            try:
                boom = ET.fromstring(r.content)
            except ET.ParseError:
                continue
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            kinderen = boom.findall("s:sitemap", ns)
            if kinderen:
                # meest recente deel-sitemaps eerst
                lijst = sorted(
                    ((k.findtext("s:loc", "", ns).strip(), k.findtext("s:lastmod", "", ns)) for k in kinderen),
                    key=lambda x: x[1] or "", reverse=True)
                wachtrij.extend(l for l, _ in lijst if l)
                continue
            for u in boom.findall("s:url", ns):
                loc = (u.findtext("s:loc", "", ns) or "").strip()
                if loc and not SKIP_EXT.search(loc) and not SKIP_PAD.search(loc):
                    urls[loc] = (u.findtext("s:lastmod", "", ns) or "")[:10]
                if len(urls) >= 6000:
                    break
        if urls:
            return urls
    return None


def pagina_titel(url):
    r = haal_op(url, timeout=15)
    if r and "html" in r.headers.get("Content-Type", ""):
        m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.I | re.S)
        if m:
            return schoon(m.group(1), 160)
    slug = urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ").replace("_", " ").capitalize() or url


GEBRUIKTE_DOMEINEN = {}


def website_publicaties(bedrijf, terugblik, status_archief):
    """Geeft (lijst, statuslabel) terug."""
    website = bedrijf["website"].strip()
    if not website:
        return [], "geen website ingevuld"
    if not website.startswith("http"):
        website = "https://" + website
    domein = urllib.parse.urlparse(website).netloc.replace("www.", "")
    vandaag = dt.date.today()
    resultaten, methodes = [], []

    home = haal_op(website)
    if not home:
        return [], "website onbereikbaar"
    echt_domein = urllib.parse.urlparse(home.url).netloc.replace("www.", "")
    eigenaar = GEBRUIKTE_DOMEINEN.setdefault(echt_domein, bedrijf["bedrijf"])
    if eigenaar != bedrijf["bedrijf"]:
        return [], f"zelfde website als {eigenaar} ({echt_domein}), overgeslagen"
    domein = echt_domein
    website = f"{urllib.parse.urlparse(home.url).scheme}://{urllib.parse.urlparse(home.url).netloc}/"
    kanalen = vind_kanalen(home.text)
    if kanalen:
        status_archief.setdefault("kanalen", {})[bedrijf["bedrijf"]] = kanalen

    for feed_url in zoek_website_feeds(website, home.text):
        items = lees_feed(feed_url, "Website", domein)
        if items:
            methodes.append("feed")
            resultaten += [i for i in items if i["datum"] and (vandaag - i["datum"]).days <= terugblik]

    robots = haal_op(urllib.parse.urljoin(website, "/robots.txt"))
    sitemap = lees_sitemap(website, robots.text if robots else "")
    if sitemap:
        methodes.append("sitemap")
        gekend = set(status_archief.get(domein, []))
        huidige = {maak_id(u) for u in sitemap}
        if gekend:
            al_gevonden = {i["url"].rstrip("/") for i in resultaten}
            nieuw = [u for u in sitemap if maak_id(u) not in gekend and u.rstrip("/") not in al_gevonden]
            nieuw.sort(key=lambda u: sitemap[u], reverse=True)
            for u in nieuw[:MAX_NIEUWE_PAGINAS]:
                try:
                    datum = dt.date.fromisoformat(sitemap[u]) if sitemap[u] else vandaag
                except ValueError:
                    datum = vandaag
                resultaten.append({
                    "titel": pagina_titel(u), "url": u, "datum": datum, "medium": domein,
                    "samenvatting": "", "bron": "Website",
                })
        status_archief[domein] = sorted(gekend | huidige)

    if not methodes:
        return resultaten, "geen feed of sitemap gevonden"
    label = " + ".join(methodes)
    if "sitemap" in methodes and not status_archief.get(domein + "#gestart"):
        status_archief[domein + "#gestart"] = [vandaag.isoformat()]
        label += " (nulmeting: nieuwe pagina's vanaf volgende week)"
    return resultaten, label


# ---------------------------------------------------------------- sociale kanalen op de website

KANAAL_PATRONEN = {
    "linkedin": re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(company|showcase|school)/([A-Za-z0-9_\-%.]{2,100})/?(?=[\"'?#\s</])", re.I),
}
GEEN_PROFIEL = {"sharer", "share", "sharer.php", "dialog", "plugins", "tr", "p", "reel", "reels", "explore",
                "stories", "intent", "login", "home.php", "watch", "events", "groups", "photo.php", "profile.php"}


def vind_kanalen(html_tekst):
    """Zoekt de officiële LinkedIn-bedrijfspagina op een webpagina.
    Bij meerdere kandidaten wint de link die het vaakst voorkomt."""
    gevonden = {}
    for kanaal, patroon in KANAAL_PATRONEN.items():
        tel = {}
        for m in patroon.finditer(html_tekst):
            if kanaal == "linkedin":
                url = f"https://www.linkedin.com/{m.group(1).lower()}/{m.group(2)}/"
            else:
                naam = m.group(1)
                if naam.split("/")[0].lower() in GEEN_PROFIEL:
                    continue
                url = f"https://www.{kanaal}.com/{naam}/"
            tel[url] = tel.get(url, 0) + 1
        if tel:
            gevonden[kanaal] = max(tel, key=tel.get)
    return gevonden


# ---------------------------------------------------------------- hoofdprogramma

def lees_bedrijven():
    with open(ROOT / "bedrijven.csv", encoding="utf-8-sig", newline="") as f:
        rijen = list(csv.DictReader(f, delimiter=";"))
    bedrijven = []
    for r in rijen:
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        if not r.get("bedrijf"):
            continue
        r.setdefault("zoeknamen", r["bedrijf"])
        r["zoeknamen"] = r.get("zoeknamen") or r["bedrijf"]
        for veld in ("groep", "website", "context", "extra_feeds", "linkedin"):
            r.setdefault(veld, "")
        bedrijven.append(r)
    return bedrijven


def lees_linkedin():
    pad = ROOT / "linkedin_manueel.csv"
    if not pad.exists():
        return []
    with open(pad, encoding="utf-8-sig", newline="") as f:
        rijen = list(csv.DictReader(f, delimiter=";"))

    def getal(x):
        try:
            v = float(str(x).replace(".", "").replace(" ", "").replace(",", ".").strip())
            return int(v) if v.is_integer() else v
        except ValueError:
            return None

    return [{
        "week": (r.get("week") or "").strip(),
        "bedrijf": (r.get("bedrijf") or "").strip(),
        "volgers": getal(r.get("volgers", "")),
        "posts": getal(r.get("posts", "")),
        "reacties": getal(r.get("reacties", "")),
        "opmerking": (r.get("opmerking") or "").strip(),
    } for r in rijen if (r.get("bedrijf") or "").strip()]


def main():
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)
    archief = json.loads(ARCHIEF.read_text("utf-8")) if ARCHIEF.exists() else []
    status_archief = json.loads(SITEMAP_STATUS.read_text("utf-8")) if SITEMAP_STATUS.exists() else {}
    eerste_run = not archief
    terugblik = TERUGBLIK_EERSTE_RUN if eerste_run else TERUGBLIK_NORMAAL
    if not status_archief.get("versie_vermeldingen2"):
        # Eenmalig opnieuw 4 maanden terugkijken nu ook vermeldingen in de artikeltekst meetellen
        terugblik = TERUGBLIK_EERSTE_RUN
        status_archief["versie_vermeldingen2"] = [dt.date.today().isoformat()]
    artikels_geopend = {}
    teller = {"geopend": 0, "vermeld": 0}
    vandaag = dt.date.today()
    log(f"Start benchmark {vandaag} - terugblik {terugblik} dagen")

    bedrijven = lees_bedrijven()
    # Ruim ook eerder verzamelde persartikels op die niet over het bedrijf gaan
    per_naam = {b["bedrijf"]: b for b in bedrijven}
    voor = len(archief)
    archief = [p for p in archief
               if p.get("kanaal") != "Pers & nieuws" or p.get("vermelding") or (
                   p["bedrijf"] in per_naam and
                   is_bedrijfsnieuws(per_naam[p["bedrijf"]], p["titel"], p.get("samenvatting", ""), p.get("medium", "")))]
    if len(archief) < voor:
        log(f"Opgeruimd: {voor - len(archief)} persartikels die niet over het bedrijf gingen")
    bekende_ids = {p["id"] for p in archief}
    bekende_titels = {(p["bedrijf"], normaliseer_titel(p["titel"])) for p in archief}
    run_status = []
    nieuw_totaal = 0

    for b in bedrijven:
        naam = b["bedrijf"]
        kandidaten, status = [], {}

        g = google_nieuws(b, terugblik)
        status["google"] = "ok" if g is not None else "fout"
        kandidaten += g or []

        bi = bing_nieuws(b)
        status["bing"] = "ok" if bi is not None else "fout"
        kandidaten += bi or []

        try:
            w, status["website"] = website_publicaties(b, terugblik, status_archief)
        except Exception as fout:  # één kapotte website mag de run niet stoppen
            w, status["website"] = [], f"fout: {type(fout).__name__}"
        kandidaten += w

        for feed_url in [f.strip() for f in b["extra_feeds"].split("|") if f.strip()]:
            items = lees_feed(feed_url, "Extra feed", urllib.parse.urlparse(feed_url).netloc.replace("www.", ""))
            if items is None:
                items = volg_nieuwspagina(feed_url, status_archief) or []
            kandidaten += [i for i in items if i["datum"] and (vandaag - i["datum"]).days <= terugblik]

        gevonden = status_archief.get("kanalen", {}).get(naam, {})
        if not b.get("linkedin") and gevonden.get("linkedin"):
            b["linkedin"] = gevonden["linkedin"]
            b["_automatisch"] = ["linkedin"]

        toegevoegd = 0
        for k in kandidaten:
            if not k["url"] or not k["titel"]:
                continue
            datum = k["datum"] or vandaag
            if (vandaag - datum).days > terugblik or datum > vandaag + dt.timedelta(days=1):
                continue
            pid = maak_id(naam + "|" + k["url"].split("#")[0].rstrip("/"))
            tkey = (naam, normaliseer_titel(k["titel"]))
            if pid in bekende_ids or tkey in bekende_titels:
                continue
            is_pers = k["bron"] in ("Google Nieuws", "Bing Nieuws")
            if is_pers and not is_bedrijfsnieuws(b, k["titel"], k["samenvatting"], k["medium"]):
                # Naam niet (zakelijk) in de titel: open het artikel en zoek de vermelding in de tekst
                if RUIS.search(k["titel"]) or artikels_geopend.get(naam, 0) >= MAX_ARTIKELS_PER_BEDRIJF:
                    continue
                artikels_geopend[naam] = artikels_geopend.get(naam, 0) + 1
                fragment, echte = vermelding_in_artikel(b, k["url"])
                teller["geopend"] += 1
                if not fragment:
                    continue
                teller["vermeld"] += 1
                k["samenvatting"] = fragment
                k["vermelding"] = True
                if echte:
                    k["url"] = echte
                    pid = maak_id(naam + "|" + echte.split("#")[0].rstrip("/"))
                    if pid in bekende_ids:
                        continue
            archief.append({
                "id": pid,
                "bedrijf": naam,
                "datum": datum.isoformat(),
                "week": iso_week(datum),
                "titel": k["titel"],
                "url": k["url"],
                "medium": k["medium"],
                "bron": k["bron"],
                "kanaal": "Pers & nieuws" if is_pers else "Eigen kanalen",
                "themas": bepaal_themas(k["titel"] + " " + k["samenvatting"]),
                "naam_in_titel": naam_in_tekst(b, k["titel"]) if is_pers else True,
                "samenvatting": k["samenvatting"],
                **({"interacties": k["interacties"]} if k.get("interacties") is not None else {}),
                **({"vermelding": True} if k.get("vermelding") else {}),
            })
            bekende_ids.add(pid)
            bekende_titels.add(tkey)
            toegevoegd += 1

        nieuw_totaal += toegevoegd
        run_status.append({"bedrijf": naam, "nieuw": toegevoegd, **status})
        log(f"  {naam:<24} +{toegevoegd:<3} google={status['google']} bing={status['bing']} website={status['website']}")

    grens = (vandaag - dt.timedelta(days=BEWAARTERMIJN_DAGEN)).isoformat()
    archief = sorted((p for p in archief if p["datum"] >= grens), key=lambda p: p["datum"], reverse=True)

    ARCHIEF.write_text(json.dumps(archief, ensure_ascii=False, indent=1), "utf-8")
    SITEMAP_STATUS.write_text(json.dumps(status_archief, ensure_ascii=False), "utf-8")
    with open(DATA_DIR / "kanalen_gevonden.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["bedrijf", "linkedin", "bron"])
        for b in bedrijven:
            auto = b.get("_automatisch", [])
            w.writerow([b["bedrijf"], b.get("linkedin", ""),
                        "automatisch van website" if auto else ("bedrijven.csv" if b.get("linkedin") else "niet gevonden")])

    dashboard = {
        "bijgewerkt": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "bedrijven": [{"naam": b["bedrijf"], "groep": b["groep"] or "Bedrijf", "website": b["website"],
                       "kanalen": {"linkedin": b["linkedin"]} if b.get("linkedin") else {},
                       "kanalen_auto": b.get("_automatisch", [])}
                      for b in bedrijven],
        "status": run_status,
        "themas": list(THEMAS.keys()) + ["Overige"],
        "publicaties": archief,
        "linkedin": lees_linkedin(),
    }
    (DOCS_DIR / "data.js").write_text(
        "window.BENCHMARK = " + json.dumps(dashboard, ensure_ascii=False) + ";\n", "utf-8")
    log(f"Artikels geopend om vermeldingen te zoeken: {teller['geopend']}, waarvan met vermelding: {teller['vermeld']}")
    log(f"Klaar: {nieuw_totaal} nieuwe publicaties, {len(archief)} in archief.")

    if all(s["google"] == "fout" and s["bing"] == "fout" for s in run_status):
        log("WAARSCHUWING: geen enkele nieuwsbron bereikbaar.")
        sys.exit(1)


if __name__ == "__main__":
    main()
