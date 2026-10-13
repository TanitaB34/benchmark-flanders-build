# Digitale benchmark Flanders Build

Elke maandagochtend verzamelt deze tool automatisch en gratis alle publieke publicaties over de bedrijven uit `bedrijven.csv` en werkt het dashboard bij.

**Wat wordt verzameld**

| Bron | Hoe | Automatisch? |
|---|---|---|
| Pers en nieuws | Google Nieuws en Bing Nieuws (openbare RSS-feeds) | Ja |
| Eigen website | Nieuwsfeed (RSS) en nieuwe pagina's via de sitemap | Ja |
| Extra pagina's | Nieuws-, blog- of projectenpagina's die je toevoegt | Ja |
| LinkedIn | Volgers, posts en reacties die je wekelijks invult via het dashboard (`linkedin_manueel.csv`) | Nee, LinkedIn verbiedt automatisch ophalen |

---

## Eenmalige installatie (ongeveer 15 minuten)

### 1. Maak een gratis GitHub-account
Ga naar https://github.com/signup en maak een account aan, bij voorkeur met je werkmailadres.

### 2. Maak een nieuwe opslagplaats (repository)
1. Klik rechtsboven op **+** en kies **New repository**.
2. Naam: `benchmark-flanders-build`.
3. Kies **Public** als je het dashboard via een weblink wil openen (gratis). Kies **Private** als niemand buiten jou het mag zien; zie dan stap 7B.
4. Klik op **Create repository**.

### 3. Upload de bestanden
1. Klik op de link **uploading an existing file**.
2. Pak het zip-bestand uit op je computer en sleep **alle bestanden en mappen** uit de map `benchmark-flanders-build` naar het uploadvenster.
3. Klik onderaan op **Commit changes**.

> **Let op de verborgen map `.github`.** Op Mac en soms op Windows is die map onzichtbaar en wordt ze dan niet mee geüpload. Controleer in GitHub of je de map `.github` ziet. Zie je ze niet:
> 1. Klik op **Add file → Create new file**.
> 2. Typ als naam: `.github/workflows/wekelijkse-benchmark.yml`
> 3. Open het bestand `workflow-kopie/wekelijkse-benchmark.yml` uit de zip met Kladblok of Teksteditor, kopieer alles en plak het in GitHub.
> 4. Klik op **Commit changes**.

### 4. Geef de automatische taak schrijfrechten
**Settings → Actions → General**, scrol naar **Workflow permissions**, kies **Read and write permissions** en klik op **Save**.

### 5. Start de eerste verzameling
1. Ga naar het tabblad **Actions**. Klik eventueel op de groene knop om workflows toe te staan.
2. Kies links **Wekelijkse benchmark** en klik rechts op **Run workflow → Run workflow**.
3. Na 15 à 30 minuten verschijnt een groen vinkje. De eerste keer kijkt de tool 4 maanden terug, zodat je meteen historiek hebt.

### 6. Zet het dashboard online (enkel bij een publieke opslagplaats)
**Settings → Pages**. Bij **Source** kies je **Deploy from a branch**, branch **main**, map **/docs**, en klik op **Save**. Na een paar minuten staat je dashboard op:
`https://JOUW-GEBRUIKERSNAAM.github.io/benchmark-flanders-build/`
Bewaar die link als favoriet.

### 7B. Bij een private opslagplaats
Klik op de hoofdpagina op **Code → Download ZIP**, pak uit en open `docs/index.html` in je browser. Doe dit opnieuw wanneer je de recentste cijfers wil.

**Klaar.** Vanaf nu draait de verzameling elke maandagochtend vanzelf.

### 8. Het dashboard ook in Claude tonen (optioneel)

Hetzelfde dashboard staat ook als artifact in Claude. Een Claude-artifact kan zelf niets van GitHub ophalen, dus je laadt de gegevens er één keer per week in (1 minuut):

1. Open in GitHub de map `docs` en klik op `data.js`.
2. Klik rechtsboven op het downloadicoon (**Download raw file**).
3. Open het dashboard in Claude, klik op **Gegevens laden** en kies het gedownloade `data.js`.

Het dashboard toont meteen de nieuwe cijfers en onthoudt ze. Collega's met wie je het artifact deelt, zien dezelfde gegevens. Alleen jij als eigenaar ziet de knop **Gegevens laden**.

---

## Dagelijks gebruik

- **Dashboard openen:** via je favoriete link. Kies periode, kanaal of thema bovenaan.
- **Excel downloaden:** knop rechtsboven. De Excel volgt de filters die je op dat moment gekozen hebt en bevat de tabbladen Rangschikking, Publicaties, Trend per week en (indien ingevuld) LinkedIn.
- **Tussentijds bijwerken:** Actions → Wekelijkse benchmark → Run workflow.

## Bedrijven aanpassen
Open `bedrijven.csv` in GitHub en klik op het potloodje (of bewerk het in Excel en upload het opnieuw). Kolommen, gescheiden door `;`:

| Kolom | Betekenis |
|---|---|
| bedrijf | Naam zoals ze in het dashboard verschijnt |
| groep | `Eigen bedrijf` voor Verstraete.team, `Sectororganisatie` voor Embuild en Buildwise (tellen standaard niet mee), en voor de anderen een segment naar keuze (bv. `Aannemer`, `Studiebureau`, `Architect`). Met de segmentfilter in het dashboard vergelijk je dan bv. enkel met aannemers |
| website | Volledig webadres, bv. `https://www.cordeel.be`. Leeg = enkel nieuws |
| zoeknamen | Exacte namen om op te zoeken, gescheiden door `|` |
| context | Optioneel. Extra woorden waarvan er minstens één moet voorkomen, gescheiden door `|`. Handig bij namen die ook iets anders betekenen (bv. Wally, Denys) |
| extra_feeds | Optioneel, gescheiden door `|`. Een RSS-feed (bv. YouTube: `https://www.youtube.com/feeds/videos.xml?channel_id=KANAAL-ID`) of een nieuws-, blog- of projectenpagina zonder RSS (bv. `https://www.mobble.be/blog`). Bij zo'n pagina meldt de tool elke nieuwe link eronder. Vul hier geen homepage in: die wordt al via de website gevolgd |

Extra kolommen (zoals `controle_status` of `opmerking`) mag je gerust behouden; de tool negeert ze.

**Tips voor goede zoektermen:**
- Zet in `zoeknamen` alleen namen die echt naar het bedrijf verwijzen. Algemene woorden zoals "BIM" of een gemeentenaam halen elk artikel daarover binnen.
- Laat `context` leeg bij unieke namen (Bostoen, Cordeel). Context betekent: minstens één van deze woorden moet in het artikel staan. Bij een unieke naam verlies je daardoor alleen maar artikels.
- Gebruik `context` wel bij namen die ook iets anders betekenen (Denys, EEG, BATO).

**Nog aan te vullen:** bij een aantal bedrijven staat nog geen website. Vul die aan om ook hun eigen publicaties te volgen. Het dashboard toont onder *Status van de bronnen* welke websites werken.

## LinkedIn aanvullen (optioneel, 5 minuten per week)
1. Open op LinkedIn de beheeromgeving van de Verstraete.team-bedrijfspagina → **Analytics → Competitors** en voeg daar de belangrijkste concurrenten toe.
2. Neem wekelijks de cijfers over in `linkedin_manueel.csv`, bv.:
   `2026-W42;Cordeel;12500;4;380;`
3. Ze verschijnen bij de volgende verzameling in het dashboard en de Excel.

## Goed om te weten
- **Website-opvolging:** de eerste keer neemt de tool een momentopname van elke website. Nieuwe pagina's worden pas vanaf de tweede week gemeld.
- **Thema's** worden automatisch toegekend op basis van trefwoorden. Lees ze als indicatie, niet als exacte telling.
- **Ruis:** bij algemene namen kan er een artikel tussen zitten dat over iets anders gaat. Vink in het dashboard *Enkel nieuws met de bedrijfsnaam in de titel* aan, of verscherp de kolom `context`.
- **Rode kruis in Actions?** GitHub stuurt je dan een mail. Meestal was een bron tijdelijk onbereikbaar: start de workflow gewoon opnieuw.
- **Workflow uitgeschakeld?** Als er 60 dagen niets in de opslagplaats verandert, pauzeert GitHub geplande taken. Ga dan naar Actions en klik op **Enable workflow**.
- Alle gebruikte bronnen zijn openbaar en de tool vraagt pagina's traag en beleefd op.

---

## LinkedIn-benchmark

De sociale-mediabenchmark vergelijkt enkel LinkedIn-bedrijfspagina's. De links staan in de kolom `linkedin` van `bedrijven.csv` (54 van de 59 bedrijven). Voor bedrijven zonder link zoekt de tool zelf de LinkedIn-pagina op hun website; het resultaat staat na elke run in `data/kanalen_gevonden.csv`.

LinkedIn verbiedt het automatisch ophalen van pagina's van anderen, dus de cijfers vul je zelf in. Het dashboard maakt dat zo licht mogelijk (ongeveer 10 à 15 minuten per week, of beperk je tot je belangrijkste concurrenten):

1. Open het dashboard en klik in het blok **LinkedIn** op **Cijfers invullen**.
2. Klik per bedrijf op **open ↗**, neem het aantal volgers over en, als je ze kent, het aantal posts en reacties van die week. Het vorige cijfer staat telkens in het grijs als geheugensteun. Lege regels worden overgeslagen.
3. Klik op **Download linkedin_manueel.csv**. Dat bestand bevat alle vorige weken plus de nieuwe cijfers.
4. Vervang in GitHub het bestand `linkedin_manueel.csv` door het gedownloade bestand (**Add file → Upload files**, sleep het erin en klik op **Commit changes**).

De nieuwe cijfers verschijnen na de volgende verzameling. Wil je ze meteen zien, start dan de workflow manueel via **Actions → Run workflow**.

Tip: in de beheeromgeving van jullie eigen LinkedIn-pagina staat onder **Analytics → Competitors** een overzicht van een aantal concurrenten met hun volgers en posts. Dat versnelt het invullen voor die bedrijven.
