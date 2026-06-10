# Strategy Research Roadmap

## Obiettivo

Trovare oppure respingere in modo riproducibile un edge post-costi per il
clean bot. La ricerca non deve produrre una strategia "vincente" per forza:
`NO_CANDIDATE` e un risultato valido.

## Principi vincolanti

- Il final OOS resta intatto fino al gate finale.
- Ogni tentativo e parametro testato viene contato.
- UnifiedCostModel e rischio massimo 0.005 sono obbligatori.
- Nessuna ottimizzazione verso un numero prefissato di trade.
- Nessuna modifica o abilitazione live/testnet/exchange.
- Nessun uso di chiavi private; sono consentiti solo dati storici pubblici.
- Nessuna promozione automatica al paper o live.

Riferimenti metodologici:

- Bailey et al., Probability of Backtest Overfitting:
  https://escholarship.org/uc/item/4w1110bb
- Bailey e Lopez de Prado, Deflated Sharpe Ratio:
  https://papers.ssrn.com/abstract=2460551
- Moskowitz, Ooi e Pedersen, Time Series Momentum:
  https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf

## STRAT-01 - Dataset expansion and research contract

Costruire un dataset riproducibile per BTC, ETH, XRP, SOL e BNB:

- target: almeno quattro anni quando disponibili;
- timeframe segnale 15m e timeframe esecuzione 5m;
- solo candele chiuse da endpoint pubblici;
- cache atomiche, manifest con hash, range, righe, gap e provenienza;
- separazione temporale immutabile train/validation/final-OOS;
- final-OOS almeno 20% e mai usato nelle patch di ideazione;
- se lo storico minimo non e disponibile, dichiararlo senza sintetizzare dati.

La patch puo scaricare dati pubblici, ma non puo usare credenziali private,
avviare bot o inviare ordini.

## STRAT-02 - Three falsifiable hypotheses

Implementare in un laboratorio separato dal runtime soltanto tre famiglie:

1. volatility breakout: segnale 15m, esecuzione causale 5m;
2. trend pullback: ingresso su ritracciamento dentro trend 15m;
3. cross-sectional momentum: selezione relativa fra i cinque asset.

Vincoli:

- massimo 12 configurazioni economicamente motivate per famiglia;
- parametri dichiarati prima del test validation/OOS;
- nessun uso del final OOS per score, ranking, shortlist o modifica strategia;
- stessa interfaccia trade e UnifiedCostModel;
- report di densita segnali, turnover, cost-to-edge e risultati train/validation;
- nessuna integrazione nel paper/live in questa fase.

## STRAT-03 - Robust selection and edge decision

Valutare tutte le prove registrate e correggere la selezione multipla:

- walk-forward e final OOS intatto;
- Deflated Sharpe Ratio;
- Probability of Backtest Overfitting mediante CSCV;
- parameter plateau, non singolo optimum;
- costi conservative e severe almeno 2x;
- concentrazione temporale e contributo dei top trade;
- confronto multi-asset e per regime.

Un candidato passa soltanto se, nel final OOS post-costi:

- almeno 50 trade;
- profit factor > 1.20;
- net PnL > 0;
- max drawdown <= 15%;
- Deflated Sharpe probability >= 0.95;
- PBO < 0.50;
- scenario severe ancora positivo;
- top 3 trade <= 35% del profitto lordo positivo;
- gate temporale superato;
- nessuna contaminazione final-OOS.

Il report deve dichiarare esplicitamente `edge_demonstrated=true/false`.

## STRAT-04 - Paper candidate readiness

Se e solo se STRAT-03 dimostra un edge:

- congelare configurazione e hash del candidato;
- integrare il candidato nel clean paper runner dietro flag disabilitato;
- collegare il feed WebSocket pubblico al paper runner;
- produrre comando e checklist per campagna supervisionata;
- mantenere live/testnet/exchange disabilitati.

Se nessun candidato passa, produrre `NO_CANDIDATE`, non integrare alcuna
strategia e non abbassare i gate.

## STRAT-PAPER-01 - Campagna paper supervisionata

Gate manuale, non completabile automaticamente:

- durata minima 8 settimane;
- almeno 50 trade osservati realmente;
- costi e fill registrati;
- PF > 1.20, PnL positivo e drawdown <= 15%;
- nessun drift rilevante rispetto al final OOS.

Solo dopo questo gate puo essere proposta una roadmap testnet. Il live reale
resta fuori scope.
