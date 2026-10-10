# Ką dabar įkelti į GitHub?

**Yra jau paleista Streamlit programėlė?** Naujo Deploy kurti nereikia. Tiesiog atnaujinkite GitHub saugyklą `liaubaite/app_shedule`.

**Būtinai pakeiskite / pridėkite šiuos tris pagrindinius failus:**

- `app.py` – atnaujinta programėlė.
- `vaizdas.py` – naujos HTML stiliaus kortelės.
- `interface_stilius.css` – tamsus meniu, šviesiai pilkas fonas ir kitų elementų stilius.

Galite įkelti visus ZIP failus (išskleistus), bet ne ZIP archyvą kaip vieną failą. `.streamlit/config.toml` rekomenduojamas, tačiau CSS pats keičia fono spalvą.

Po `Commit changes` atnaujinkite Streamlit puslapį. Jei trūksta vieno iš naujų failų, pasirodys `ModuleNotFoundError` arba `FileNotFoundError` – patikrinkite, kad trys failai yra **tame pačiame kataloge**.

⚠ **Duomenys:** jei Supabase dar nesukonfigūruota ir jau įvedėte svarbius įrašus, prieš įkeldami naują kodą eksportuokite juos į Excel. Programos perkrovimas gali ištrinti vietinę SQLite saugyklą.
