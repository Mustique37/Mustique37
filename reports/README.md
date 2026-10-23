# Chauffeursstatistieken

Rapport per chauffeur voor het platform "Intercargo x Krëfel".

1. Haal de cijfers op in de database van het platform:
   `SELECT public.driver_stats('2026-10-18', '2026-10-24') AS data;`
   De functie staat in `driver_stats.sql`.
2. Bewaar de uitvoer als JSON en maak de PDF:
   `python3 reports/driver_report.py data.json rapport.pdf "Chauffeursstatistieken week 18/10 – 24/10" "18 t/m 24 oktober 2026"`
3. Naast de PDF komt `rapport.berichten.txt` met een bericht per chauffeur, klaar voor WhatsApp.

Regels:
- Een stop telt bij chauffeur en bijrijder.
- "Niet uitgepakt" = stop met "niet uitgepakt" aangeduid, behalve als de reden toont dat uitpakken niet van toepassing was
  (afhaling in de winkel, interventie, installatie wel gebeurd). Percentage op de afzetten zonder installatie.
- Ritten die de dispatch achteraf aanmaakte, tellen niet mee voor open stops.
- Klachten = klachtdossiers over ritten in de periode, plus dossiers die in de periode binnenkwamen over oudere ritten.
