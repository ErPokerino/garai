# GarAI su Google Cloud Run

Versione cloud (branch `cloud`) pensata per una POC: un solo servizio Cloud Run, dati su Cloud Storage, nessuna licenza
Microsoft.

## Come si ottiene il PowerPoint senza PowerPoint

| Funzione | Desktop (Windows) | Cloud Run (Linux) |
|---|---|---|
| Creazione del PPTX | python-pptx (clona e riempie il template) | identica |
| Misura del testo per il ciclo di fit | PowerPoint via COM: misura reale | stima con i font del template (Work Sans) e margine di sicurezza del 4% (`ESTIMATE_WIDTH_MARGIN`) |
| Anteprime delle slide | PowerPoint | LibreOffice headless (PPTX → PDF → PNG) |

Il file scaricato è un PPTX nativo e si apre in PowerPoint con i font installati sul PC. Le anteprime nell'app sono
generate da LibreOffice e possono differire di poco dall'impaginazione di PowerPoint.
Nell'immagine sono installati Work Sans (OFL, in `assets/fonts/`), Clash Display (se presente in
`assets/fonts/private/`: licenza non ridistribuibile, quindi esclusa da git), Liberation (metriche di Arial/Helvetica)
e Carlito (metriche di Calibri).

## Architettura

```
utente ──HTTPS──► Cloud Run "garai" (1 istanza, CPU sempre allocata)
                    │  FastAPI + frontend React + LibreOffice
                    │  cartella dati locale /data  ◄──ripristino all'avvio / replica ogni 5 s──►  gs://<progetto>-garai-data
                    ├─ Secret Manager: garai-session-secret, garai-gemini-key
                    └─ Gemini API
```

- **Persistenza**: l'app lavora su disco locale come in desktop; `app/cloud_sync.py` ripristina la cartella dati dal
  bucket all'avvio e replica ogni 5 secondi i file nuovi, modificati ed eliminati (il registro costi SQLite con l'API
  di backup). Allo spegnimento dell'istanza fa un'ultima replica.
- **Una sola istanza** (`max-instances=1`): è l'unica a scrivere i dati; elaborazioni in background con CPU sempre
  allocata e `min-instances=1`, così non si interrompono quando il browser è chiuso.
- **Isolamento**: tutte le risorse hanno prefisso `garai` ed etichetta `app=garai`. I service account dedicati hanno
  permessi solo sulle risorse garai (bucket, repository, secret), nessun ruolo di progetto oltre alla scrittura dei log
  di build.
- **Accesso**: il servizio è pubblico (`--allow-unauthenticated`); l'app richiede comunque il login.
  `TRUSTED_PROXY_HOPS=1` fa usare l'IP reale del client (aggiunto dal proxy di Google) per il blocco dei tentativi.
- **Limite di spesa mensile**: 20 USD di default (`MONTHLY_BUDGET_USD`), modificabile da Impostazioni.

## Deploy

Requisiti: `gcloud` autenticato con un account owner del progetto. Non serve Docker in locale (build con Cloud Build).

```bash
GCP_ACCOUNT=me@example.com GEMINI_API_KEY=... bash deploy/gcp.sh
```

Lo script è idempotente: crea solo ciò che manca, poi build e deploy. `SKIP_SETUP=1` per rifare solo build e deploy.

## Costi indicativi

Istanza sempre attiva (2 vCPU, 2 GiB): circa 3,5 USD al giorno. Storage, build e secret: centesimi. Le chiamate
Gemini sono registrate nella pagina Costi dell'app.

## Rimozione completa

```bash
P=tutoral-498710; R=europe-west1
gcloud run services delete garai --region=$R --project=$P
gcloud artifacts repositories delete garai --location=$R --project=$P
gcloud storage rm -r gs://$P-garai-data gs://$P-garai-build
gcloud secrets delete garai-session-secret --project=$P
gcloud secrets delete garai-gemini-key --project=$P
gcloud projects remove-iam-policy-binding $P --member=serviceAccount:garai-build@$P.iam.gserviceaccount.com --role=roles/logging.logWriter --condition=None
gcloud iam service-accounts delete garai-run@$P.iam.gserviceaccount.com --project=$P
gcloud iam service-accounts delete garai-build@$P.iam.gserviceaccount.com --project=$P
```

## Evoluzioni se la POC prosegue

- Misura più fedele: posizioni reali del testo dal PDF di LibreOffice, oppure conversione con il motore Microsoft via
  Graph API (licenza M365 aziendale).
- Dati su Firestore/Cloud SQL al posto della replica su bucket, per avere più istanze.
- Elaborazioni su Cloud Run Jobs o Cloud Tasks; accesso con Google Workspace (IAP) invece della password.
