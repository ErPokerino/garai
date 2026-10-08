# Analisi della repo e refactoring (ottobre 2026)

## 1. Punto di partenza

POC Python (~3.000 righe) con una pipeline ben progettata e una UI Streamlit.

**Da preservare** (ed è stato preservato senza modifiche sostanziali):

- separazione netta tra ciò che fa l'LLM (estrarre, abbinare, riassumere, valutare) e ciò che è deterministico (anni di esperienza, ordinamento, nomi segnaposto, etichette, impaginazione);
- template **clonato e riempito**, mai ricreato: fedeltà grafica garantita;
- **ciclo di fit su misura reale** (PowerPoint COM) con riscrittura LLM e poi riduzione deterministica;
- verifica di fedeltà al CV; fixture per i test offline.

**Problemi rilevati**

| # | Area | Problema | Impatto |
|---|---|---|---|
| T1 | LLM | Il client Anthropic forzava `tool_choice` su uno strumento: con i modelli Claude attuali (Sonnet/Opus 5.5) restituisce **errore 400** | Bloccante all'aggiornamento dei modelli |
| T2 | LLM | Nessun conteggio di token né di costi; nessun limite di spesa | Costi invisibili |
| T3 | Config | Chiavi e modelli solo da `.env`, letti all'import: cambiare provider richiedeva il riavvio | UX, manutenzione |
| T4 | Architettura | UI e orchestrazione accoppiate in Streamlit; stato solo in sessione (perso al refresh); nessuno storico | Affidabilità, UX |
| T5 | Config | `MAX_FIT_ITERATIONS` documentato ma mai usato dalla pipeline | Parametro inefficace |
| T6 | Concorrenza | Generazioni parallele avrebbero aperto PowerPoint (COM) in contemporanea | Rischio di blocchi |
| F1 | Prodotto | Nessuna stima di costo prima della generazione | Decisioni al buio |
| F2 | Prodotto | La gap analysis (copertura dei requisiti) esisteva solo nel report Markdown | Valore nascosto |
| F3 | Prodotto | Nessun modo di correggere a mano un testo generato senza rigenerare tutto con l'LLM | Costo e tempo |
| F4 | Prodotto | Un solo provider per volta tra Anthropic/OpenAI; nessun Gemini | Scelta limitata |

## 2. Cosa è stato fatto

### Tecnico

- **Layer LLM riscritto** (`app/llm/`):
  - `providers.py`: Anthropic con **structured outputs** (`messages.parse`), OpenAI, **Gemini** (`google-genai`, `response_json_schema` + `thinking_level`); ripiego automatico su JSON nel prompt se un modello non supporta lo schema, e sul ragionamento di default se il livello richiesto non è accettato; retry con backoff sugli errori transitori Gemini (429/5xx).
  - Ogni chiamata restituisce l'**Usage** (input non in cache, output incluso ragionamento, cache letta/scritta, latenza, tentativi).
  - `pricing.py`: listino versionato per data (gestisce l'aumento di Gemini 3.8 Flash dal 2027), override da UI.
  - `usage.py`: **registro SQLite** di ogni chiamata, aggregazioni (giorno, modello, attività, pratica, fase) e **limiti di spesa** per pratica e mensili.
  - La cache su disco conserva il consumo originale: i riusi sono registrati come **risparmio**.
  - Schemi resi portabili tra provider (schema JSON autocontenuto; `Translation` da mappa a lista di coppie).
- **Configurazione a runtime** (`app/config.py`): impostazioni da UI salvate in `data/settings.json` con precedenza su `.env`; chiavi mai restituite in chiaro dall'API.
- **Backend FastAPI** (`app/api/server.py`) + **servizio pratiche** (`app/service/runs.py`): stato persistente su disco, job in background, **eventi SSE** per avanzamento e costi in tempo reale, ripristino dopo riavvio, lock unico sul renderer PowerPoint.
- Pipeline: fasi etichettate per il costo, progresso per CV, **`rebuild()`** da contenuti modificati, note di impaginazione separate dagli avvisi, `MAX_FIT_ITERATIONS` collegato.
- Streamlit rimosso.

### Funzionale

- **Nuovo frontend** React + TypeScript + Tailwind (tema chiaro/scuro, responsive): pratiche, nuova pratica con drag & drop, workspace con stepper, revisione abbinamenti, risultato, costi, impostazioni.
- **Stima del costo** prima di generare (intervallo min–max sulla base della dimensione reale dei CV e del listino del modello scelto).
- **Gap analysis visuale** per candidato (soddisfatti / parziali / non evidenziati, con evidenze), affermazioni da verificare, riduzioni applicate.
- **Editor dei contenuti** + **ricostruzione** del deck senza nuove chiamate AI.

### Test

`tests/test_llm_costs.py` (listino, registro, limiti, cache, client Gemini con SDK simulato) e `tests/test_api.py` (flusso API completo con risposte preregistrate, incluse modifica e ricostruzione), oltre ai test esistenti.

## 3. Roadmap consigliata

In ordine di valore/sforzo.

1. **Prima esecuzione reale con Gemini** sui 6 CV di esempio: confrontare report e slide con le fixture, affinare i prompt, misurare il costo per CV (la pagina Costi lo dà già). È il passo più importante: oggi la qualità dei prompt su un modello reale non è stata verificata.
2. **Eval di regressione dei prompt**: congelare le uscite "buone" del punto 1 come riferimento e confrontare automaticamente a ogni modifica dei prompt o cambio di modello (copertura requisiti, affermazioni non supportate, overflow).
3. **Ottimizzazione costi**:
   - l'estrazione del bando usa il modello principale per ogni profilo (14 chiamate sul bando di esempio): valutare il modello veloce, oppure mettere in cache il bando già analizzato e riusarlo tra pratiche dello stesso bando;
   - il verificatore riceve tutto il testo del CV a ogni revisione: valutare la cache del prompt del provider (implicita su Gemini, esplicita su Claude) con il CV come prefisso stabile;
   - Batch API (50% di sconto) per pratiche non urgenti.
4. **Bando riutilizzabile**: libreria di bandi già analizzati, a cui aggiungere CV nel tempo senza ripetere l'estrazione.
5. **Editor degli abbinamenti multipli**: più candidati sullo stesso profilo con confronto affiancato della copertura, per scegliere chi proporre.
6. **Template personalizzati**: oggi lo Spec proposto dall'AI non è revisionabile dalla UI; aggiungere un editor visuale degli slot con anteprima.
7. **Esportazione PDF** della presentazione e del report di gap analysis per il bid manager.
8. **Multi-utente** (solo se serve): autenticazione, pratiche per utente, segreti in un vault invece che su file; oggi l'app è volutamente locale.
