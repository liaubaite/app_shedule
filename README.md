# Darbo grafikų skaičiuoklė

Darbo grafikų programa (Diana, Renata, Vilma; Žiogeliai ir Žirniukai), pritaikyta Streamlit Cloud ir Supabase. Pagrindinės funkcijos: 30 val. = 100%, individualios pamainos, mėnesio kalendoriai, valstybinės šventės, atostogos, pavadavimai, atskiri grupių balansai ir skolų perkėlimas, Excel eksportas, užrakinti pastovūs grafikai.

**Supabase ryšio pataisymas:** daugiau neberodomas nepaaiškinamas `RuntimeError` dėl HTTP atsakymo; matomas HTTP statusas, klaidų paaiškinimai, saugus prisijungimo pakartojimas, suderinamumas su naujais `sb_secret_...` raktais ir projektiniu `/rest/v1/` URL. Jei įrašas nepersiunčiamas į nuotolinę bazę, vartotojas informuojamas ir gali pakartoti įrašymą.

Diegimas: žr. [PRADĖKITE.md](PRAD%C4%96KITE.md). Tikro `secrets.toml` failo nekelkite į GitHub.

Testai: `python -m unittest discover -p 'test_*.py'`.
