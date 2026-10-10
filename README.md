# Darbo grafikų skaičiuoklė – atnaujinta HTML išvaizda

Ši versija yra **tikra Streamlit programėlė**, kurios stilius ir išdėstymas kiek įmanoma priartinti prie ankstesnės lietuviškos HTML demonstracijos (tamsus kairysis meniu, šviesiai pilkas fonas, baltos kortelės, mėlynas / geltonas grupių akcentas, vienos darbuotojos ataskaita su dviem atskirais skaitiniais stulpeliais).

**Pastaba:** tai Streamlit komponentais įgyvendinta HTML dizaino adaptacija, ne tas pats HTML dokumentas. Kaip tiksliai atrodys patys įvedimo laukai ir meniu, priklauso nuo Streamlit / naršyklės versijos. Dėl to tikslus pikselis į pikselį atitikimas nėra garantuojamas.

## Kas išliko

- Diana, Renata ir Vilma; 100 % = 30 val. per savaitę.
- Pastovūs 12 val. grafikai ir atskiri pradiniai Žiogelių / Žirniukų etato procentai.
- Mėnesinė apskaita nuo 2026 m. spalio, pradinė skola 0 val.
- Tik darbo dienos (Pr–Pn); Lietuvos šventės – visoms laisvos ir be skolų.
- Atostogų / ligos registravimas, atostogų laikotarpio etatas iki 150 %, pavadavimai, skolos dengimas, valandų pakeitimai ir įrašų trynimas su patvirtinimu.
- Asmeninės mėnesio ataskaitos su **porinėmis skolomis atskirai abiejose grupėse**, skolų likučių perkėlimu ir Excel eksportu.
- Atskirų grupių bei darbuotojų mėnesio kalendoriai.
- Užrakinti pastovūs grafikai; galima sąmoningai atrakinti.

## Kas vizualiai pakeista

- **Mano ataskaita** yra pirmasis ekranas, jo viršuje pasirenkamas mėnuo ir darbuotoja.
- Ataskaita rodoma **baltoje kortelėje**: Žiogeliai, Žirniukai, planas, faktas, balansas, duomenų lentelė pagal kitas dvi koleges.
- **Mėnesio grafikas** pirmiausia rodo **pasirinktą darbuotoją**; po ja – dvi grupes. Kitų darbuotojų grafikai ir suvestinės išskleidžiami, kad būtų paprasta naudotis.
- **Pastovūs grafikai** – trys kortelės, po vieną kiekvienai darbuotojai, kaip HTML pavyzdyje.
- **Mėnesio pakeitimai** vis dar įvedami tikrais Streamlit laukais, todėl jų pavidalas gali nežymiai skirtis nuo HTML.

## GitHub (kai programėlė jau paleista)

1. Prieš atnaujinimą: **jei jau yra realių įvestų pakeitimų ir nėra sukonfigūruota Supabase, pirmiausia išsisaugokite Excel**. Streamlit Cloud vietinis SQLite failas po programos atnaujinimo gali būti prarastas.
2. Išskleiskite ZIP kompiuteryje. GitHub saugyklos `liaubaite/app_shedule` pagrindiniame aplanke pakeiskite / įkelkite:
   - `app.py` (pakeiskite esamą)
   - `vaizdas.py` (**naujas failas**)
   - `interface_stilius.css` (**naujas failas**)
3. `grafiko_logika.py`, `grafiko_rodymas.py`, `saugykla.py` lieka tie patys, bet ZIP įdėtos tinkamos jų versijos, jei reikėtų atnaujinti visus.
4. Kad fonas sutaptų su HTML demonstracija, galima papildomai įkelti `.streamlit/config.toml` (nebūtina, CSS jau naudojamas pačiame `app.py`).
5. Paspauskite **Commit changes**. Streamlit Cloud turėtų automatiškai iš naujo paleisti programą. Jei ne – `Manage app → Reboot app`.
6. Įsitikinkite, kad Streamlit **Secrets** išliko tie patys. Jų nekelkite į GitHub.

## Duomenų saugojimas

Slaptažodžiai ir Supabase prieiga turi likti **Streamlit Secrets**, o ne GitHub. Kol Supabase neįjungta, Streamlit Cloud vis dar perspės apie vietinę SQLite ir pasikeitimų praradimo riziką. Dizaino atnaujinimas **šios rizikos nepašalina**.

## Paleidimas lokaliai

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Testai:

```bash
python -m unittest discover -p 'test_*.py' -v
```

Kodų skaičiavimo testai sėkmingi. Šioje kūrimo aplinkoje nėra Streamlit bibliotekos, todėl nauja gyva Streamlit sąsaja dar nepatikrinta naršyklėje po diegimo.
