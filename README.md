# GarAI: CV su template PPT, guidato dal bando

Input: **bando** (DOCX/PDF), **CV** eterogenei (DOCX/PDF), **template PPTX** richiesto dalla gara (se manca si usa quello Abstract).
Output: **una sola PPTX** con tutti i CV inseriti nel template, riassunti e riordinati in funzione del profilo richiesto dal bando, nella lingua del bando, più un **report** (copertura dei requisiti, nomi inventati, tagli per spazio, verifica di fedeltà).

## Avvio rapido

```powershell
.\avvia.ps1
```

Lo script installa le dipendenze al primo avvio, compila il frontend e apre http://127.0.0.1:8765.
Accesso iniziale: utente `admin`, password `123` (si cambia da **Impostazioni → Il tuo account**).
Poi: **Impostazioni** → scegli il provider (Gemini, Claude o OpenAI), incolla la API key, **Prova connessione**, e crea una pratica caricando bando e CV.

Avvio manuale:

```powershell
pip install -r requirements.txt
cd web; npm install; npm run build; cd ..
python -m app            # --port 8765 --no-browser --reload
```

Sviluppo frontend con hot reload: `python -m app --no-browser` in un terminale e `cd web; npm run dev` in un altro (http://localhost:5173, le chiamate `/api` vanno al backend).

## Flusso nell'app

1. **Nuova pratica**: carica bando + CV (+ template della gara). L'analisi parte subito; avanzamento e costo si vedono in tempo reale.
2. **Revisione**: profili e requisiti estratti dal bando; abbinamento CV → profilo/variante proposto dall'AI con affidabilità e motivazione, modificabile. **Nome del candidato** inseribile o correggibile (evidenziato quando il CV non lo riporta; se resta vuoto ne viene inventato uno). **Stima del costo** della generazione prima di avviarla. In **Dati e indicazioni** si correggono ruolo attuale, sede e contatti, si danno **indicazioni per la scrittura** (per candidato e per tutti: cosa mettere in evidenza, cosa evitare) e si può **escludere** un candidato. Dalla presentazione generata si torna a questo passo con «Rivedi abbinamenti e indicazioni».
3. **Generazione**: scrittura dei contenuti, verifica di fedeltà, impaginazione sul template con misura reale, rendering delle slide.
4. **Risultato**: download PPTX e report, anteprima slide, per ogni candidato la **copertura dei requisiti** (soddisfatti / parziali / non evidenziati), le affermazioni da verificare e le riduzioni applicate. I contenuti si possono **modificare a mano** e la presentazione si **ricostruisce senza nuove chiamate AI**.

Le pratiche restano salvate in `data/runs/` e sono consultabili dallo storico anche dopo un riavvio.

## Modelli e costi

| Provider | Principale (default) | Veloce (default) |
|---|---|---|
| Google Gemini | `gemini-3.8-flash` | `gemini-3.5-flash-lite` |
| Anthropic | `claude-sonnet-5-5` | `claude-haiku-5-5` |
| OpenAI | `gpt-5` | `gpt-5-mini` |

Il modello **principale** fa estrazione del bando, parsing dei CV, scrittura e critico visivo; quello **veloce** abbinamento, verifica di fedeltà e traduzione etichette. Modelli e livello di ragionamento si scelgono per livello dalle Impostazioni.

**Monitoraggio costi** (pagina *Costi*): ogni chiamata è registrata in `data/garai.db` con token di input/output/ragionamento/cache, durata e costo calcolato sul listino in vigore quel giorno. Spesa giornaliera o cumulativa per modello (con i modelli selezionabili dalla legenda), per attività della pipeline, per pratica; costo medio per CV; risparmio della cache locale (una richiesta identica non viene ripetuta e non costa). Listino nel codice (`app/llm/pricing.py`), con eventuali correzioni via API in `data/pricing.json`. **Limiti di spesa** per pratica e mensili: al raggiungimento le chiamate si fermano con un messaggio chiaro.

Nota sul listino Gemini: i prezzi di Gemini 3.8 Flash ($0,75 / $3,75 per milione di token in/out) **raddoppiano dal 1° gennaio 2027**; il calcolo ne tiene già conto.

## Come funziona

```
bando ─► estrazione profili/requisiti (LLM) ─┐
CV ────► parsing in JSON canonico (LLM) ─────┼─► abbinamento CV↔profilo(+variante) ─► Writer LLM con budget di spazio
                                              │        ─► verifica di fedeltà (LLM) ─► riempimento del template ORIGINALE
template ► Template Spec (JSON) + budget ─────┘        ─► misura reale del testo (PowerPoint) ─► ciclo di fit ─► PPTX + report
```

Scelte chiave:

- **Il template non viene ricreato**: le slide originali sono clonate e riempite (`python-pptx` + lxml), quindi font, colori, loghi e icone restano identici. Il template Abstract ha **2 slide per persona** (profilo + esperienze): lo Spec in `templates/abstract_cv.spec.json` descrive gli slot.
- **Layout garantito da misure, non dall'LLM**: i limiti di spazio sono calcolati dal template e passati al Writer; il testo reale viene misurato su PowerPoint (COM) e, se serve, riscritto o tagliato in modo deterministico.
- **Nessuna invenzione**: il Writer può solo riformulare/selezionare; un verificatore segnala affermazioni non supportate dal CV.
- **Output strutturato nativo** per ogni provider (schema JSON imposto lato server), con ripiego automatico su "JSON nel prompt" se un modello non lo supporta.
- **Interfaccia** sull'identità visiva di abstract.it: Funnel Sans + Work Sans, viola `#7355ec` e arancio `#ff7800`, tema chiaro/scuro.
- **Renderer** per misura/anteprima: PowerPoint (Windows) > LibreOffice > stima Pillow. Forzabile con `RENDERER=powerpoint|libreoffice|estimate`.

## Struttura

```
app/
  api/server.py        API FastAPI + hosting del frontend (web/dist)
  service/runs.py      pratiche: stato persistente, job in background, eventi SSE
  service/estimate.py  stima dei costi prima della generazione
  llm/                 provider (Anthropic, OpenAI, Gemini), cache, listino, registro costi e limiti di spesa
  pipeline/            estrazione bando, parsing CV, matching, writer, verifica, fit, report
  template/ render/ ingestion/ schemas/
web/                   frontend React + TypeScript + Tailwind (Vite)
run_cli.py             uso da riga di comando
```

CLI:

```powershell
python run_cli.py --bando bando.docx --cv cv1.docx cv2.pdf --out out/run
# offline, con risposte LLM preregistrate (cartella di fixture):
python run_cli.py --bando bando.docx --cv cv1.docx cv2.pdf --fixtures samples/fixtures
```

Test: `python -m pytest` (unit, auth, layer LLM e costi con SDK simulati, API). I test end-to-end di generazione usano bando e CV reali in `samples/` con risposte preregistrate: **la cartella non è versionata** (contiene dati personali), quindi su un clone del repository quei test vengono saltati.

## Stato della validazione (leggere!)

- Le fasi LLM sono state eseguite con Gemini su pratiche reali (circa $0,03 per CV); i prompt in `app/llm/prompts.py` vanno comunque affinati sui casi che emergono dall'uso.
- Verificati con dati reali: ingestione DOCX/PDF, riempimento fedele del template, misura reale con PowerPoint, nessun overflow residuo, flusso completo dalla UI, modifica manuale e ricostruzione.
- Il critico visivo è **solo segnalazione** (non modifica le slide).
- **Template qualsiasi**: per un template diverso da quello Abstract un LLM con visione descrive gli spazi da compilare (titoli, righe "Etichetta: valore", elenchi, paragrafi, anche campi non previsti come "Lingue" o "Disponibilità"); `app/template/normalize.py` corregge e completa la proposta (shape inesistenti, campi, etichette, limite del piè di pagina, font del template) e una costruzione di prova la valida prima della scrittura. Nessuno slot è obbligatorio: budget, riempimento e riduzioni dipendono solo dagli slot presenti.
- **Accesso**: tutte le API richiedono login. Password salvate come hash scrypt (`data/users.json`), sessione in cookie firmato HttpOnly/SameSite=Strict (Secure in HTTPS) con scadenza a 12 ore, protezione CSRF sull'origine delle richieste, blocco temporaneo dopo tentativi falliti, cambio password che chiude le altre sessioni. Per la messa online: `GARAI_SECRET_KEY` (chiave di firma delle sessioni) e `GARAI_ADMIN_PASSWORD` (password iniziale al posto di `123`) da un gestore di segreti; `python -m app --host 0.0.0.0` dietro HTTPS.
- Le API key dei provider sono conservate sul server in `data/settings.json` e non vengono mai restituite in chiaro.

Versione cloud (Google Cloud Run, senza PowerPoint): [docs/CLOUD.md](docs/CLOUD.md).

Analisi della repo e piano di evoluzione: [docs/REFACTORING.md](docs/REFACTORING.md).
