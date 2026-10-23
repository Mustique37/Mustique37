#!/usr/bin/env python3
"""Chauffeursstatistieken Intercargo x Krëfel -> PDF.

Gebruik:
  python3 reports/driver_report.py <data.json> <uit.pdf> "<titel>" "<periode-tekst>"

<data.json> is de uitvoer van de databasefunctie public.driver_stats(van, tot)
(Supabase-project van "Intercargo x Krefel"). Het script maakt een HTML-rapport,
zet het met Chromium om naar PDF en schrijft de berichten per chauffeur ook
naar <uit>.berichten.txt (klaar om via WhatsApp door te sturen).
"""
import glob, html, json, os, subprocess, sys

def chrome():
    if os.path.exists('/opt/pw-browsers/chromium'):
        return '/opt/pw-browsers/chromium'
    c = sorted(glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome'))
    return c[-1] if c else 'chromium'

e = lambda s: html.escape(str(s if s is not None else ''))
def pct(a, b): return (100.0 * a / b) if b else 0.0
def fp(v): return f"{v:.1f}".replace('.', ',') + '%'
def nl(n): return f"{n:,}".replace(',', '.')

CAT = {'klant': 'op vraag klant', 'buren': 'bij buren / klant afwezig', 'nvt': 'niet van toepassing', 'andere': 'andere reden'}

def build(data, title, period):
    T, S = data['totaal'], data['stops']
    people = [p for p in (data.get('personen') or []) if (p['stops'] or p['rc'] or p['rb'] or p['klachten'])]
    for p in people:
        p['nu_echt'] = p['nu'] - p['nu_nvt']
        p['pct'] = pct(p['nu_echt'], p['afzet'])
    nu_echt = S['nu'] - S['nu_nvt']
    avg = pct(nu_echt, S['afzet'])

    def tile(v, l, sub=''):
        return f'<div class="tile"><div class="v">{v}</div><div class="l">{e(l)}</div><div class="s">{e(sub)}</div></div>'
    tiles = ''.join([
        tile(nl(T['ritten']), 'ritten', f"{T['ic']} thuislevering · {T['cc']} Click & Collect"),
        tile(nl(S['stops']), 'stops', f"{nl(S['inst'])} installaties · {nl(S['afzet'])} afzetten"),
        tile(fp(avg), 'niet uitgepakt', f"{nu_echt} van {nl(S['afzet'])} afzetten · {S['nu_klant']} op vraag klant"),
        tile(f"{S['pend']}", 'stops niet afgewerkt in app', 'op afgesloten ritten'),
        tile(f"{sum(1 for k in (data.get('klachten') or []) if k['rit_in_periode'])}", 'klachten over deze periode', f"{sum(1 for k in (data.get('klachten') or []) if not k['rit_in_periode'])} binnengekomen over oudere ritten"),
        tile(f"{S['rating'] or '–'}".replace('.', ','), 'klantscore op 5', f"{S['n_rating']} beoordelingen"),
    ])

    # 1. ranglijst niet uitgepakt
    rk = sorted([p for p in people if p['afzet'] >= 5], key=lambda p: (-p['nu_echt'], -p['pct']))
    def cls(p):
        if p['pct'] >= max(avg * 1.5, 1): return 'bad'
        if p['pct'] > avg: return 'warn'
        return ''
    r1 = ''.join(f"<tr class='{cls(p)}'><td>{e(p['naam'])}</td><td>{p['afzet']}</td><td><b>{p['nu_echt']}</b></td><td><b>{fp(p['pct'])}</b></td><td>{p['nu_klant']}</td><td>{p['nu_buren']}</td><td>{p['nu_andere']}</td></tr>" for p in rk)

    # 2. overzicht per persoon
    ov = sorted(people, key=lambda p: (-p['stops'], -(p['rc'] + p['rb'])))
    r2 = ''.join(
        f"<tr><td>{e(p['naam'])}</td><td>{p['rc']} / {p['rb']}</td><td>{p['stops']}</td><td>{p['inst']}</td><td>{p['afzet']}</td>"
        f"<td class='{cls(p)}'>{p['nu_echt']} · {fp(p['pct'])}</td>"
        f"<td class='{'bad' if p['pend'] >= 5 else ''}'>{p['pend']}</td><td>{p['afw']}</td><td class='{'bad' if p['klachten'] else ''}'>{p['klachten']}</td><td>{(str(p['rating']).replace('.', ',') + ' (' + str(p['n_rating']) + ')') if p['n_rating'] else '–'}</td></tr>"
        for p in ov)


    # 4. stops niet afgewerkt
    r4 = ''.join(f"<tr><td>{e(x['dag'])}</td><td>{e(x['ride_number'])}</td><td>{e(x['ploeg'])}</td><td><b>{x['pending']}</b></td></tr>" for x in (data.get('pending_ritten') or [])) or "<tr><td colspan='4'>Geen</td></tr>"

    # 5. klachten
    r5 = ''.join(f"<tr class='{'bad' if k['rit_in_periode'] else ''}'><td>{e(k['ontvangen'])}</td><td>{e(k['ritdag'] or '–')}</td><td>{e(k['chauffeur'] or '–')}</td><td>{e(k['bijrijder'] or '–')}</td><td>{e(k['titel'])}</td><td>{e(k['status'])}</td></tr>" for k in (data.get('klachten') or [])) or "<tr><td colspan='6'>Geen klachten</td></tr>"

    # 6. weken
    wk = data.get('weken') or []
    import datetime as dt
    pv, pt = dt.date.fromisoformat(str(data['van'])), dt.date.fromisoformat(str(data['tot']))
    def wlabel(w):
        d0 = max(dt.date.fromisoformat(w), pv); d1 = min(dt.date.fromisoformat(w) + dt.timedelta(days=6), pt)
        return f"{d0:%d/%m} – {d1:%d/%m}"
    r6 = ''.join(f"<tr><td>{wlabel(w['wk'])}</td><td>{w['ritten']}</td><td>{w['stops']}</td><td>{w['afzet']}</td><td>{w['nu']}</td><td>{fp(pct(w['nu'], w['afzet']))}</td></tr>" for w in wk)

    # bijlage: lijst niet uitgepakt
    rl = ''.join(f"<tr class='{'muted' if x['cat']=='nvt' else ''}'><td>{e(x['dag'])}</td><td>{e(x['ride_number'])}</td><td>{e(x['customer_name'])}<br><span class='small'>{e(x['city'])}</span></td><td>{e(x['ploeg'])}</td><td>{e(CAT.get(x['cat'], x['cat']))}</td><td>{e((x['reden'] or '(geen reden)')[:180])}</td></tr>" for x in (data.get('niet_uitgepakt') or []))

    # berichten per chauffeur
    msgs = []
    for p in sorted([p for p in people if p['stops'] or p['rc']], key=lambda p: p['naam'] or ''):
        lines = [f"*{p['naam']}* – {period}",
                 f"Ritten: {p['rc']} als chauffeur, {p['rb']} als bijrijder" + (f" ({p['cc']} Click & Collect)" if p['cc'] else ''),
                 ]
        if p['stops']:
            lines.append(f"Stops: {p['stops']} ({p['inst']} installaties, {p['afzet']} afzetten)")
            lines.append(f"Niet uitgepakt: {p['nu_echt']} ({fp(p['pct'])} van je afzetten, gemiddelde {fp(avg)})")
            lines.append(f"Stops niet afgewerkt in de app: {p['pend']}")
        lines.append(f"Klachten: {p['klachten']}")
        if p['n_rating']:
            lines.append(f"Klantscore: {str(p['rating']).replace('.', ',')}/5 ({p['n_rating']} beoordelingen)")
        tips = []
        if p['afzet'] and p['pct'] > avg and p['nu_echt'] >= 3:
            tips.append("Pak elk toestel uit bij de klant. Alleen als de klant het echt weigert, laat je het verpakt en noteer je duidelijk waarom.")
        if p['pend']:
            tips.append("Werk elke stop af in de app: foto's, uitpakken en handtekening.")
        if p['klachten']:
            tips.append("Er kwam een klacht binnen over een rit van jou. De dispatch neemt contact op.")
        if not tips:
            tips.append("Goed gewerkt, ga zo door! 👍")
        lines += ['⚠️ ' + t if not t.startswith('Goed') else t for t in tips]
        msgs.append('\n'.join(lines))
    def mfmt(m):
        first, _, rest = m.partition('\n')
        return '<b>' + e(first.replace('*', '')) + '</b><br>' + e(rest).replace(chr(10), '<br>')
    mhtml = ''.join(f"<div class='msg'>{mfmt(m)}</div>" for m in msgs)

    css = """
@page { size:A4; margin:13mm 12mm 15mm 12mm;
 @bottom-left { content:"Intercargo · Chauffeursstatistieken"; font:7pt 'Liberation Sans',Arial,sans-serif; color:#6b7280; }
 @bottom-right { content:"Pagina " counter(page) " / " counter(pages); font:7pt 'Liberation Sans',Arial,sans-serif; color:#6b7280; } }
*{box-sizing:border-box} body{font:8.6pt/1.4 'Liberation Sans','DejaVu Sans',Arial,sans-serif;color:#111827;margin:0}
.top{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid #0f2a4a;padding-bottom:2.5mm;margin-bottom:4mm}
.brand{font-weight:700;font-size:11pt;color:#0f2a4a;letter-spacing:.5px} .meta{font-size:8pt;color:#374151;text-align:right}
h1{font-size:17pt;color:#0f2a4a;margin:0 0 1mm} .sub{color:#374151;font-size:9.5pt;margin-bottom:4mm}
h2{font-size:11.5pt;color:#0f2a4a;margin:6mm 0 2mm;padding-bottom:1mm;border-bottom:1.5px solid #dbe3ee;break-after:avoid}
p{margin:0 0 2mm} .note{font-size:7.8pt;color:#4b5563} .small{font-size:7pt;color:#6b7280}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:2.5mm;margin-bottom:2mm}
.tile{border:1px solid #dbe3ee;border-radius:2mm;padding:2.2mm 2.8mm;background:#f8fafc}
.tile .v{font-size:15pt;font-weight:700;color:#0f2a4a} .tile .l{font-weight:600;font-size:8.2pt} .tile .s{font-size:7.2pt;color:#6b7280}
table{width:100%;border-collapse:collapse;font-size:7.9pt;margin:1mm 0 2mm}
th{background:#0f2a4a;color:#fff;text-align:left;padding:1.3mm 1.6mm;font-weight:600;font-size:7.5pt}
td{border-bottom:1px solid #e5e7eb;padding:1.1mm 1.6mm;vertical-align:top} tr{break-inside:avoid}
tr.bad td, td.bad{background:#fde8e8} tr.warn td, td.warn{background:#fff6e0} tr.muted td{color:#6b7280}
.pb{break-before:page}
.msgs{columns:2;column-gap:4mm} .msg{break-inside:avoid;border:1px solid #d1d5db;border-left:3px solid #0f2a4a;border-radius:1.5mm;padding:2mm 2.5mm;margin:0 0 3mm;font-size:8pt;background:#fafafa}
"""
    body = f"""
<div class="top"><div class="brand">INTERCARGO</div><div class="meta">{e(period)}</div></div>
<h1>{e(title)}</h1>
<div class="sub">Bron: onze app. Ritten, stops, notities bij niet uitpakken en klachtdossiers.</div>
<div class="tiles">{tiles}</div>
<p class="note">Een stop telt bij beide ploegleden: chauffeur en bijrijder. “Niet uitgepakt” telt de stops waarbij de ploeg “niet uitgepakt” aanduidde, behalve wanneer de reden toont dat uitpakken niet van toepassing was, zoals afhaling in de winkel, een interventie of een installatie die wel gebeurde. Het percentage is berekend op de afzetten zonder installatie.</p>

<h2>1. Wie heeft het vaakst niet uitgepakt?</h2>
<table><tr><th>Naam</th><th>Afzetten</th><th>Niet uitgepakt</th><th>% van afzetten</th><th>Op vraag klant</th><th>Buren / afwezig</th><th>Andere reden</th></tr>{r1}</table>
<p class="note">Rood = minstens anderhalve keer het gemiddelde van {fp(avg)}. Oranje = boven het gemiddelde. De redenen per stop staan in bijlage A.</p>

<h2>2. Overzicht per persoon</h2>
<table><tr><th>Naam</th><th>Ritten chauf. / bijr.</th><th>Stops</th><th>Install.</th><th>Afzetten</th><th>Niet uitgepakt</th><th>Stops niet in app</th><th>Afwijk.</th><th>Klachten</th><th>Klantscore</th></tr>{r2}</table>
<p class="note">“Afwijkingen” zijn stops met een afwijkingscode; die liggen niet altijd aan de ploeg.</p>

<h2>3. Stops niet afgewerkt in de app</h2>
<table><tr><th>Dag</th><th>Rit</th><th>Ploeg</th><th>Stops open</th></tr>{r4}</table>
<p class="note">Stops die nog op “wachtend” stonden toen de rit afgesloten werd. Ritten die de dispatch zelf aanmaakte, tellen niet mee.</p>

<h2>4. Klachten</h2>
<table><tr><th>Binnen</th><th>Ritdag</th><th>Chauffeur</th><th>Bijrijder</th><th>Klacht</th><th>Status</th></tr>{r5}</table>
<p class="note">Rood = klacht over een rit in deze periode. De andere klachten kwamen in deze periode binnen maar gaan over oudere ritten.</p>

{('<h2>5. Per week</h2><table><tr><th>Week (zo – za)</th><th>Ritten</th><th>Stops</th><th>Afzetten</th><th>Niet uitgepakt</th><th>%</th></tr>' + r6 + '</table>') if len(wk) > 1 else ''}

<h2 class="pb">Bijlage A – Alle stops niet uitgepakt</h2>
<table><tr><th>Dag</th><th>Rit</th><th>Klant</th><th>Ploeg</th><th>Soort</th><th>Reden volgens de ploeg</th></tr>{rl}</table>

<h2 class="pb">Bijlage B – Berichten per chauffeur</h2>
<p class="note">Klaar om door te sturen via WhatsApp.</p>
<div class="msgs">{mhtml}</div>
"""
    return f"<!doctype html><html lang='nl'><head><meta charset='utf-8'><title>{e(title)}</title><style>{css}</style></head><body>{body}</body></html>", msgs

def main():
    src, out, title, period = sys.argv[1:5]
    data = json.load(open(src))
    if isinstance(data, dict) and 'rows' in data:
        data = data['rows'][0]['data']
    if isinstance(data, str):
        data = json.loads(data)
    page, msgs = build(data, title, period)
    htmlp = os.path.splitext(out)[0] + '.html'
    open(htmlp, 'w').write(page)
    open(os.path.splitext(out)[0] + '.berichten.txt', 'w').write('\n\n'.join(msgs))
    subprocess.run([chrome(), '--headless=new', '--no-sandbox', '--disable-gpu', '--no-pdf-header-footer',
                    f'--print-to-pdf={out}', 'file://' + os.path.abspath(htmlp)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('ok', out)

if __name__ == '__main__':
    main()
