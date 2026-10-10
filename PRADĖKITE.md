# Darbo grafikų skaičiuoklė – Supabase prisijungimo pataisymas

## Kodėl programa išmesdavo RuntimeError?

Ankstesnis `saugykla.py` sukurdavo pradinę GET užklausą į Supabase ir, gavęs 401 / 403 / 404 / kitą atsakymą, sukeldavo neapdorotą klaidą. Todėl Streamlit rodė tik „This app has encountered an error“. Tikroji HTTP klaidos reikšmė buvo matoma tik serverio žurnale.

Ši versija **neatspėja klaidos priežasties**, o parodo HTTP kodą ir Supabase techninį kodą, jei jis pateiktas. Tikrasis raktas ar HTTP atsakymo duomenys nerodomi. Jei ryšys neveikia, programa neleidžia klaidingai manyti, kad pakeitimai išsaugoti Supabase.

## A. Įkelti pataisytus failus į GitHub

1. Atidarykite `https://github.com/liaubaite/app_shedule`.
2. `Add file` → `Upload files`.
3. Išskleiskite ZIP. Įkelkite išskleistus failus į saugyklos **pagrindinį aplanką**, ne ZIP archyvą.
4. Ypač svarbūs `saugykla.py` ir `app.py` (abiejų naujos versijos).
5. Pasirinkite `Commit changes` ir palaukite Streamlit programėlės automatinio paleidimo.

## B. Patikrinti Streamlit Secrets

Programėlė → Settings → Secrets:

```toml
GRAFIKAS_ADMIN_PASSWORD = "NAUJAS-STIPRUS-SLAPTAZODIS"
SUPABASE_URL = "https://JUSU-PROJEKTAS.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "sb_secret_JUSU_NAUJAS_RAKTAS"
```

Raktą rinkitės iš **Supabase → Project Settings → API Keys → Secret keys**. Naudoti tik serverio Secret raktą, ne Publishable. Kadangi ankstesnis tikras raktas ir slaptažodis buvo įrašyti pokalbyje, rekomenduojama abu pakeisti ir senąjį raktą panaikinti. Niekada nekelkite realių raktų į GitHub.

## C. Supabase SQL Editor

Atsidarykite Supabase projektą → **SQL Editor** → įklijuokite ir vykdykite `supabase_sukurti_lentele.sql` turinį.

SQL nekeičia ir netrina jau esančių `app_state` duomenų. Suteikiama `service_role` reikalinga prieiga, o `anon` ir `authenticated` prieiga panaikinama.

## D. Paleisti ir patikrinti

1. Streamlit Cloud pasirinkite **Reboot app**.
2. Jei prisijungimas nepavyksta, dabar matysite **HTTP kodą**, pvz. 401 (netinkamas raktas), 403 (teisės), 404 (lentelė / URL / Data API), o ne tuščią RuntimeError.
3. Jei prisijungimas pavyksta, įveskite bandomąjį mėnesio pakeitimą ir patikrinkite Supabase → **Table Editor → app_state**, ar yra įrašas `id = main`. Įrašykite, perkraukite serverį ir patikrinkite, ar pakeitimas išliko. Po patikrinimo bandomąjį pakeitimą ištrinkite.

## Saugumas

Tai serverinio Streamlit ir Supabase sujungimas. Tikras `sb_secret` raktas lieka tik Streamlit Secrets. Ši versija vis dar saugo visą SQLite turinį vienoje nuotolinėje eilutėje `app_state/main` – tinka mažai programėlei su vienu redaktoriumi; keliems vienu metu redaguojantiems naudotojams reikėtų atskiro daugianaudotojo duomenų modelio.
