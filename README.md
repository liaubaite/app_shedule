# Darbo grafikų skaičiuoklė — Diana, Renata, Vilma

Lietuviška Python / Streamlit darbo grafikų ir mėnesinių tarpusavio valandų likučių programa. Du skirtingi valandų balansai: **Žiogeliai** ir **Žirniukai**. Apskaita nuo **2026-10-01**, ankstesnių skolų nėra.

## Paleidimas

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Vietiniam bandymui galima nustatyti `GRAFIKAS_ALLOW_DEMO=1` aplinkos kintamąjį. Viešam Streamlit Community Cloud diegimui būtina nustatyti `GRAFIKAS_ADMIN_PASSWORD`, `GRAFIKAS_VIEW_PASSWORD`, `GRAFIKAS_VIEW2_PASSWORD` ir patvarią saugyklą pagal `streamlit_secrets_PAVYZDYS.toml` bei `supabase_sukurti_lentele.sql`. Niekada nedėkite slaptažodžių ar raktų į GitHub. SQLite failas be patvarios saugyklos gali būti prarastas debesijos platformos perkrovimo metu.

## Patvirtinti pradiniai duomenys

- **100 % = 30 valandų per savaitę.** Abiem grupėms po 200 %; bendras darbuotojos krūvis gali būti iki 150 %.
- **Diana:** Žiogeliai 75 %, Žirniukai 50 %. An 12 val. Žiogeliuose, Tr 12 val. Žirniukuose, Kt 12 val. Žiogeliuose.
- **Renata:** Žiogeliai 125 %, Žirniukai 0 %. Pr, Tr ir Pn po 12 val. Žiogeliuose.
- **Vilma:** Žiogeliai 0 %, Žirniukai 150 %. Pr, An, Kt, Pn po 12 val. Žirniukuose.
- Darbo dienos rodomos tik Pr–Pn; grafikas automatiškai kartojamas pagal tikrą mėnesio kalendorių.
- **Lietuvos valstybinės šventės: laisvos visoms.** Jei šventė sutampa su darbuotojos pastovia 12 val. pamaina, ne tik faktinės tos dienos valandos yra 0, bet ir jos individualus skolų planas sumažinamas **12 val.**. Šventės nepažymimos kaip atostogų / ligos valandos, jų metu neleidžiami pavadavimai ar viršvalandžių koregavimas. Šventės nesukuria skolos ar tariamų papildomų valandų. Tai **tarpusavio balanso koregavimas**, o ne darbo teisės ar apmokėjimo normos nustatymas. Pvz., 2026-11-02 Renata ir Vilma neturi įprastų 12 val. pamainų ir nei viena nelieka skolinga 12 val.

- Pastovus savaitinis grafikas ir sutartinis etato procentas yra **atskiri parametrai**. Nėra reikalavimo, kad kiekvieną savaitę sutaptų jų valandos; mėnesio planas skaičiuojamas iš procento ir mėnesio dienų normos.
- Pradiniai grafikai yra užrakinti; keisti galima tik paspaudus **„Redaguoti pastovius grafikus“** ir patvirtinus saugojimą.

## Įprasti mėnesio pakeitimai

Meniu **„Mėnesio pakeitimai“**:

1. **Atostogos** – darbuotojos atostogų / ligos neatvykimas ir atostogų metu kitos darbuotojos laikinai taikomas bendras etatas (iki 150 %). Pateisintų neatvykimų valandos nesukuria asmeninės skolos.
2. **Pavadavimai ir skolų dengimas** – konkreti data, kas dirbo už ką, grupė ir valandos. Dirbtos valandos gali būti papildomos arba perkeltos iš kitos grupės. Anksčiau sukaupta skola dengiama papildomai dirbant už konkretų žmogų.
3. **Viršvalandžiai / kiti pakeitimai** – skaitinė korekcija arba atskirai saugoma laisva pastaba.
**Atostogų skiltyje – laikinas etatas** – kai per kolegės atostogas sutartu laikotarpiu kitos darbuotojos bendras etatas **padidinamas iki daugiausia 150 %**. Nurodykite darbuotoją, grupę, datas ir naują laikiną bendrą procentą. Laikinas padidinimas nekeičia bazinio grafiko ir procentų, nekuria skolų. **Papildomai faktiškai įrašytų valandų dalis iki padidėjusiai etato daliai tenkančios normos nėra laikoma viršvalandžiais ir neperkeliamas į skolų balansą.** Jei padidinto etato dalis pilnai neišdirbta, dėl jos nėra automatiškai skaičiuojama skola. Valandos, nesusijusios su padidinimo laikotarpiu, užskaitomos pagal įprastas taisykles. Jei bendras naujas procentas viršija 150 %, įvedimas neleidžiamas.

**Skaičiavimo pavyzdys:** jei darbo krūvis laikinai padidintas nuo 125 % iki 150 % dešimčiai įprastų darbo dienų, papildoma laikina norma yra `10 × 6 val. × 25 % = 15 val.`. Jei tuo laikotarpiu užregistruota 12 papildomų valandų, jos gali būti priskirtos padidintam krūviui ir neįtrauktos į skolą; neišdirbtos likusios 3 val. nesukuria neigiamo likučio. Jei užregistruota 17 papildomų valandų ir mėnesio bendra suma viršija bazinį planą, iki 15 val. nelaikoma skola, likusi dalis vertinama kaip nuokrypis.

## Mėnesio grafikai: atostogos ir visi pakeitimai

Pasirinkus mėnesį, visų trijų darbuotojų **Pr–Pn kalendoriuose** matomos faktinės valandos grupėse ir konkrečios dienos įvykiai:

- **Atostogos ir liga** (neįskaitomi nei perdirbimai, nei nedadirbimai už pateisintą neatvykimą).
- **Pavadavimas ir ankstesnės skolos dengimas**: kas už ką dirbo, kurioje grupėje ir kiek valandų. Pakeitimas matomas ir pas pavaduojantį, ir pas pavaduojamą darbuotoją.
- **Papildomos valandos, perkėlimai ir korekcijos**: rodomos su ženklu (+ / −) ir įvesta pastaba.
- **Atostogų metu taikomas laikinas etatas** (pavyzdžiui, 150 %), atskirai nuo tarpusavio skolų.
- **Lietuvos šventės**: laisva visoms, valandos nesukuria skolų.

Po kiekvienos darbuotojos kalendoriumi yra išskleidžiama **dienų lentelė**, kurioje yra stulpelis „Pakeitimai“. Laisvos mėnesio pastabos, neturinčios darbuotojos, rodomos kaip bendros pastabos po kalendoriais. Pakeitimų įrašai gali būti taisomi per „Mėnesio pakeitimus“ (pašalinant neteisingą ir įrašant teisingą). Demonstracinėje HTML peržiūroje jie lieka tik atidarytame puslapyje ir neišlieka uždarius puslapį.

## Ataskaitos

Pasirinkite **mėnesį ir vieną darbuotoją**. Matomi jos valandų planas ir faktas (atskirai abiem grupėms) ir **tarpusavio likučiai su kitomis dviem darbuotojomis** dviem skaitiniais stulpeliais „Žiogeliai (val.)“, „Žirniukai (val.)“. `+` reiškia „kolega man skolinga“, `−` – „aš skolinga kolegei“. Likučiai perkeliami nuo spalio per kitus mėnesius. Galima atsisiųsti `.xlsx` su dienos grafiku, neatvykimais, pavadavimais, laikinais etato padidinimais ir skolos istorija.

## Svarbūs apribojimai

- Ši programa skaičiuoja sutartinį darbo valandų balansą, **ne darbo užmokestį**, apmokamus viršvalandžius ar darbo teisės reikalavimus.
- **Bazinio grafiko arba procentų pakeitimas** dabar perskaičiuoja ankstesnius mėnesius; ankstesnių grafikų versijavimas pagal įsigaliojimo datas dar neįdiegtas.
- Švenčių dienos visoms laisvos, jų pamainos neutralizuojamos tarpusavio skolų plane; prieššventinių darbo dienų trumpinimas neįdiegtas.
- Jei tikras padidinto etato darbo valandų paskirstymas yra kitoks nei proporcinga darbo dienų norma, reikėtų atitinkamai patikslinti apskaitos taisyklę prieš naudojant ją darbo apmokėjimo sprendimams.
- SQL duomenis valdykite atsakingai, nes čia gali būti neatvykimų ir sveikatos duomenų. Administratorius mato tik redagavimo funkcijas, kiti gali peržiūrėti.

## Testavimas

`python -m unittest discover -p "test_*.py" -v` – 31 automatinis testas, įskaitant laikino 150 % etato viršutinę ribą ir teisingą paskaičiavimą be naujų skolų. Streamlit langas šiame kūrimo konteineryje nebuvo paleistas naršyklėje (biblioteka neįdiegta).

## Nauja: bendras mėnesio kalendorius pagal grupes ir saugus trynimas

- Skiltyje **Mėnesio grafikai → Bendras mėnesio grafikas pagal grupę** yra atskiros
  **Žiogelių** ir **Žirniukų** kortelės. Kiekviename Pr–Pn kalendoriaus langelyje
  pateikiami **visų trijų darbuotojų vardai ir faktinės valandos** (jei tos dienos
  grupėje dirba), atostogos, ligos, pavaduojantys darbuotojai ir kiti pakeitimai.
  Rodomas grupės dienos valandų skaičius. Informacija apskaičiuojama iš to paties
  mėnesio duomenų kaip ir darbuotojų grafikai, nepridedant valandų dukart.
- Kiekvienos grupės kalendoriaus apačioje galima išskleisti dienų lentelę ir
  parsisiųsti **Excel** su visų darbuotojų valandomis pagal datas.
- **Mėnesio pakeitimai:** po kiekvieno įrašo (atostogų / ligos, atostogų metu
  taikomo etato, pavadavimo, skolos grąžinimo, korekcijos ar pastabos) rodomas
  mygtukas **„🗑️ Trinti“**. Norint ištrinti būtina dar paspausti
  **„Taip, ištrinti“** (arba „Atšaukti“). Tik redaktorius gali šalinti.
  Ištrynus grafikai ir mėnesių skolų likučiai perskaičiuojami.

## Kaip pirmą kartą įkelti į GitHub ir paleisti Streamlit Cloud

**Esama saugykla:** `https://github.com/liaubaite/app_shedule`.

1. Išskleiskite pateiktą ZIP **savo kompiuteryje**. ZIP turinys yra sukomplektuotas
   taip, kad `app.py` ir `requirements.txt` būtų pagrindiniame aplanke (be papildomo
   `darbo_grafiku_skaiciuokle` poaplankio).
2. GitHub atidarykite `liaubaite/app_shedule`. Jei saugykla tuščia, spauskite
   **„uploading an existing file“**, arba eikite **Add file → Upload files**.
3. Pažymėkite ir įkelkite **išskleistus failus**, ne patį ZIP. Paspauskite
   **Commit changes**; jei pasiūloma nauja šaka, rinkitės `main`.
4. Patikrinkite, kad saugyklos viršuje matosi `app.py` ir `requirements.txt`,
   taip pat `grafiko_logika.py`, `grafiko_rodymas.py`, `saugykla.py`.
5. Streamlit Community Cloud pasirinkite **Create app**, tada:

   - Repository: `liaubaite/app_shedule`
   - Branch: `main` (arba **tikrasis** šakos pavadinimas GitHub viršuje)
   - Main file path: `app.py`
   - App URL: `tvarkarastis-app` (jei toks subdomenas dar laisvas).

6. **Advanced settings → Secrets:** įrašykite slaptažodžius pagal
   `streamlit_secrets_PAVYZDYS.toml`, nenaudodami tikrų reikšmių pačiame GitHub.
   Pavyzdys:

   ```toml
   GRAFIKAS_ADMIN_PASSWORD = "JUSU_REDAKTORIAUS_SLAPTAZODIS"
   GRAFIKAS_VIEW_PASSWORD = "JUSU_SKATYTOJOS_1_SLAPTAZODIS"
   GRAFIKAS_VIEW2_PASSWORD = "JUSU_SKATYTOJOS_2_SLAPTAZODIS"
   ```

7. **SVARBU dėl duomenų išlikimo:** Streamlit Cloud vietinis SQLite failas nėra
   patvari saugykla. Norint, kad atostogos, pavadavimai ir skolos išliktų po
   programos perkrovimo, papildomai sukurkite Supabase projektą, jo SQL Editor
   įvykdykite `supabase_sukurti_lentele.sql`, o į **Streamlit Secrets** pridėkite
   `SUPABASE_URL` ir `SUPABASE_SERVICE_ROLE_KEY`. Pastarasis yra itin jautrus
   serverio raktas – **niekada nekelkite jo į GitHub**.
8. Spauskite **Deploy**. Tik po to galėsite atidaryti programėlę ir
   įvesti mėnesio įvykius per lietuvišką sąsają.

Jeigu GitHub svetainė neleis įkelti paslėpto `.streamlit` katalogo per internetinę
sąsają, tai nėra kliūtis pirmam paleidimui: `app.py`, `requirements.txt` ir
trys pagalbiniai `.py` failai yra būtini, o `.streamlit/config.toml` – pasirenkamas.

**Sauga:** jei GitHub saugykla vieša, išsaugoti Python pradinių duomenų vardai bus
matomi viešai. Tikri darbuotojų neatvykimai / su sveikata susiję duomenys neturi
būti keliami į GitHub, jie registruojami programėlėje ir saugomi atskiroje DB.
