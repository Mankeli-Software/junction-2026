# #61 Seeded order history for demo companies: proposal

Status: agreed 2026-11-14 (Miska), recorded in `vision.md` §13. Issue: #61. Feeds #32 (seed data) and #42 (sanity checks). Refs: `vision.md` §9, §13; `technical-plan.md` §9.2, §14; `docs/specs/call-screen.md` §2.2.

**Goal**: "my usual" and "the same as last time" work on the first call, for any number a visitor types, and the history looks like a real kitchen of a recognisable kind.

## 1. Decisions (Miska, 2026-11-14)

1. **Seven kitchen types**: pizza restaurant, school kitchen, lunch restaurant, bar, vegan catering company, cafe, tech office (snacks and drinks).
2. **The type comes from the phone number**, deterministically, like the generated Oy name: the same number always gets the same company, type and history. No change to the call screen; the dashboard card can show the type.
3. **Exclusions swap, they don't drop.** The visitor still picks the kitchen's exclusions (`call-screen.md` §2.2). A history item the chosen kitchen can't have is replaced by its alternative through the category substitute map (#78: milk → oat drink, butter → margarine, mince → plant mince), so "my usual" is always orderable. If no safe alternative is found, the item is left out.
4. **Eight weeks of history, each type at its own rhythm** (table below), ending the day before the business clock's "now" (Thu 2026-11-12), so the last order is recent.

## 2. Rhythm and size

| Type | Orders | Days | Orders in 8 weeks |
|---|---|---|---|
| School kitchen | weekly | Mon | 8 |
| Lunch restaurant | twice a week | Mon, Thu | 16 |
| Pizza restaurant | twice a week | Tue, Fri | 16 |
| Bar | twice a week | Wed, Fri | 16 |
| Vegan catering | weekly | Tue | 8 |
| Cafe | three times a week | Mon, Wed, Fri | 24 |
| Tech office | every other week | Mon | 4 |

Each order has the type's **core** items always and its **sometimes** items about every other order. Quantities vary by up to ±15% around the base, rounded to a sensible step (whole sales units, 0.5 kg, 1 l). The variation and the "sometimes" choice are seeded by the phone number and the order date, so a history is the same on every run.

"My usual" is each core item with its median quantity. "The same as last time" is the latest order.

## 3. Items per type

Base quantity per order. Units are the contract's `RequestedUnit`: `l`, `kg`, `piece`, `sales_unit` (one case, bag or tray as sold). Product ids are from the catalogue (checked 2026-11-14).

### School kitchen (about 300 meals a day)

| Product | Id | Base | Core |
|---|---|---|---|
| Valio kevytmaito 1 l laktoositon UHT | 464201 | 120 l | yes |
| Atria Naudan 0 Jauheliha 10% 2 kg | 463104 | 30 kg | yes |
| Peruna pesty 1 kg | 460478 | 80 kg | yes |
| Porkkana 10 kg säkki Suomi | 460708 | 30 kg | yes |
| Keiju Catering kasvirasvalevite 70% 400 g | 460829 | 6 kg | yes |
| Oululainen Jälkiuuni Täysjyväruis 8 kpl | 462683 | 30 sales_unit | yes |
| Bama jäävuorisalaattipala 1 kg × 6 | 468185 | 12 kg | yes |
| Kieku Luomu kananmuna M 5200 g | 463883 | 10 kg | sometimes |
| Myllyn Paras Makaroni 10 kg | 462863 | 20 kg | sometimes |
| Atria Kanan Paistisuikale 3 kg | 468936 | 24 kg | sometimes |

### Lunch restaurant (about 150 lunches a day)

| Product | Id | Base | Core |
|---|---|---|---|
| Valio kevytmaito 1 l ESL | 469549 | 20 l | yes |
| Valio ruokakerma 15% 1 l UHT laktoositon | 464249 | 15 l | yes |
| Valio voi 500 g suolaamaton | 464411 | 5 kg | yes |
| Naapurin maalaiskananpojan rintafilee n 15 kg | 467238 | 15 kg | yes |
| SPL raaka yleisperuna veitsikuorittu | 475245 | 40 kg | yes |
| Sipuli 10 kg säkki Suomi | 460195 | 10 kg | yes |
| Tomaatti 1 lk Suomi | 460065 | 6 kg | yes |
| Kurkku 1 Suomi | 460137 | 5 kg | yes |
| Lohifilee n 10 kg | 461814 | 10 kg | sometimes |
| Risella pitkäriisi parboil 5 kg | 462346 | 10 kg | sometimes |

### Pizza restaurant

| Product | Id | Base | Core |
|---|---|---|---|
| Galbani Mozzarella raaste 2 kg | 471650 | 20 kg | yes |
| Caputo Pizzajauho Pizzeria 00 | 472880 | 50 kg | yes |
| Bravo Chef tomaattimurska 10 kg BIB | 466203 | 20 kg | yes |
| Karelian pizzakinkkusuikale | 467697 | 6 kg | yes |
| Argal pepperoni 1 kg | 463031 | 4 kg | yes |
| Praft ananaspala mehussa 3,035 kg | 463716 | 2 sales_unit | yes |
| Tuorehiiva 1 kg | 460039 | 2 kg | yes |
| Herkkusieni tuore 3 kg Suomi | 461266 | 6 kg | sometimes |
| Luglio extra virgin oliiviöljy 5 l | 472267 | 5 l | sometimes |
| Valio AURA® murennettu 1 kg | 476881 | 2 kg | sometimes |

### Bar

| Product | Id | Base | Core |
|---|---|---|---|
| Sitruuna 1 kg pussi | 460846 | 3 kg | yes |
| Lime | 461007 | 2 kg | yes |
| Laitilan Kukko Lager alkoholiton 24 × | 477209 | 4 sales_unit | yes |
| Coca-Cola Original 20 × | 477380 | 3 sales_unit | yes |
| Thomas Henry Tonic Water 20 cl | 477159 | 4 sales_unit | yes |
| Olvi Vichy 12 × 0,33 l | 477191 | 6 sales_unit | yes |
| Bloks jääpalat 4 kg | 461416 | 20 kg | yes |
| Sun Valley suolapähkinä 24 × 50 g | 472755 | 2 sales_unit | sometimes |
| Taffel Sips suolattu 10 × 130 g | 474485 | 2 sales_unit | sometimes |
| Ginger People inkivääriolut | 477228 | 2 sales_unit | sometimes |

### Vegan catering company

| Product | Id | Base | Core |
|---|---|---|---|
| Oddlygood® kaurajuoma 1 l | 468465 | 30 l | yes |
| Fazer Aito Oat for Cooking kauraruoka | 473956 | 20 sales_unit | yes |
| Jalotofu maustamaton tofu 1080 g | 467690 | 12 sales_unit | yes |
| Gold&Green® Härkis® härkäpapumurska | 475009 | 15 kg | yes |
| Monarch kikherne 5 × 3 kg | 474111 | 2 sales_unit | yes |
| Risella pitkäriisi parboil 5 kg | 462346 | 20 kg | yes |
| Keiju Catering rypsiöljy 10 l | 466285 | 10 l | yes |
| Sipuli 10 kg säkki Suomi | 460195 | 20 kg | yes |
| Oddlygood® grated 1 kg | 467595 | 5 kg | sometimes |
| Knorr kasvisliemi 5 kg | 461219 | 1 sales_unit | sometimes |

### Cafe

| Product | Id | Base | Core |
|---|---|---|---|
| Puro Fuerte espresso kahvipapu 1 kg | 463213 | 4 kg | yes |
| Fazer Aito Professional Barista kaurajuoma 1 l | 475224 | 12 l | yes |
| Valio kevytmaito 1 l ESL | 469549 | 20 l | yes |
| Arla kuohukerma 1 l ESL laktoositon | 464727 | 4 l | yes |
| Fazer korvapuusti 60 × 110 g raakapakaste | 476407 | 1 sales_unit | yes |
| Reuter & Stolt croissant voita | 460884 | 1 sales_unit | yes |
| Valio voi 500 g suolaamaton | 464411 | 2 kg | yes |
| DS taloussokeri 1 kg | 463161 | 3 kg | sometimes |
| Nordqvist tee 160 pss | 462475 | 1 sales_unit | sometimes |
| Fazer Jyväshyvä kaurakeksi | 467917 | 2 sales_unit | sometimes |

### Tech office (snacks and drinks)

| Product | Id | Base | Core |
|---|---|---|---|
| Paulig Presidentti tumma paahto | 474002 | 2 sales_unit | yes |
| Oddlygood® kaurajuoma 1 l | 468465 | 12 l | yes |
| Valio kevytmaito 1 l laktoositon UHT | 464201 | 12 l | yes |
| Battery energiajuoma 24 × 0,33 l | 476937 | 2 sales_unit | yes |
| Olvi Vichy 12 × 0,33 l | 477191 | 4 sales_unit | yes |
| Banaani 4,5 kg | 461010 | 9 kg | yes |
| Fazer Pätkis Crunchy proteiinipatukka | 472120 | 2 sales_unit | yes |
| Nutisal Natural Mix pähkinäsekoitus | 464990 | 2 sales_unit | sometimes |
| Taffel Sips suolattu 10 × 130 g | 474485 | 1 sales_unit | sometimes |
| Clipper luomu musta tee 20 pussia | 468473 | 2 sales_unit | sometimes |

## 4. How #32 builds it

- `data/demo_histories.yaml` holds the types, rhythms and items above; `order_history_lines` (product, quantity, unit, ordered_at, company) is filled when a demo company is created.
- The swap of decision 3 runs at account creation and again when the visitor changes the exclusions, so the history always fits the current kitchen.
- The prices and stock of history items are not stored: a reorder goes through the normal quote path.

## 5. Further decisions (Miska, 2026-11-14)

5. **The vegan catering type pre-selects the vegan exclusion** on the account screen; the visitor can still change it. The account screen is Jesse's (#54), so this is agreed with him there.
6. **A fixed stage number** (a setting, not committed) always maps to the school kitchen, so the scripted scenarios in #59 know that its usual includes lactose-free milk.
