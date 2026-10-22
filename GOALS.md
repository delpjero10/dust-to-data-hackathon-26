# GOALS — Dust to Data (Bosch Hackathon 2026)

## Vizija

Imamo **inovativno resenje** koje dodaje **AI u ceo sistem** — od mapiranja, preko
automatizacije, do prirodno-jezicke kontrole uredjaja. Koristimo mane uredjaja kao
prednost: vecina problema koje svakodnevni korisnici imaju sa robot usisivacem moze
da se resi pametnim slojem iznad hardvera.

## Glavni cilj

Pokazati da "los" uredjaj sa pravim AI slojem postaje mnogo bolji:
- **Inovativnost** — AI nije dodatak, vec je ugradjen u svaki deo sistema (data → odluka → akcija).
- **Funkcionalnost** — resavamo stvarne probleme: lose mapiranje, neoptimalno ciscenje,
  neprakticna kontrola.

## Specificni ciljevi

### 1. AI za bolje mapiranje
- Uredjaj **lose mapira** — analiziramo mape, podatke o sobama i napredak ciscenja.
- Generisemo **bolju predstavu o prostoru** nego sto je raw mapa daje (npr. detekcija
  soba, pravih prepreka, "mrtvih" zona koje su propustene).

### 2. AI automatizacija akcija
- **Automatsko pokretanje/pauziranje/zaustavljanje** ciscenja na osnovu stanja, trigera
  ili podataka (npr. raspored, zauzetost prostora, prethodne sesije).
- **Pametno planiranje** — ne cistimo "najbolje po uredjaju", nego po onome sto
  podaci kazu da je potrebno.

### 3. Prirodno-jezicka kontrola i izvestaji
- Korisnik razgovara sa uredjajem (chatbot / glas).
- AI prevodi nameru u Home Connect komande i **objasnjava sta se desava** (izvestaji).

### 4. AI u komunikaciji (end-to-end)
- AI layer **sve vreme u petlji**: citamo stanje/evente, tumacimo ih, donosimo odluke,
  saljemo komande — sve kroz Home Connect API.

## Kako merimo uspeh

- Inovativno i demonstrabilno resenje pred ziri-jem (ne samo "radi", nego "pametno radi").
- Vidljivo poboljsanje mapiranja / pokrivenosti u odnosu na stock podesavanja.
- Automatizovane akcije koje rade bez ljudske intervencije.
- Kontrola prirodnim jezikom koja je intuitivna za publiku.
- Cista, ponovljiva arhitektura koju tim moze da objasni.

## Principi

- Simulator-first: bezbedno testiranje pre realnog uredjaja.
- Belezenje i dokumentovanje svakog endpoint-a/interakcije za tim.
- Fokus na konkretan demo do kraja hackathona.
