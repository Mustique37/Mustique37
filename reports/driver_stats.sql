-- Chauffeursstatistieken per periode (Europe/Brussels), gebruikt door reports/driver_report.py
-- Aangemaakt in de Supabase-database van "Intercargo x Krefel" op 23/10/2026.
CREATE OR REPLACE FUNCTION public.driver_stats(p_from date, p_to date)
RETURNS json LANGUAGE sql STABLE SET search_path = public AS $fn$
WITH rides_p AS (
  SELECT r.*, to_char(r.end_time AT TIME ZONE 'Europe/Brussels','HH24:MI:SS') AS eind,
    (coalesce(r.manual_crew_names::text,'') ~* '(achteraf ingevoerd|toegevoegd door dispatch|rechtgezet)' OR r.vehicle_plate IN ('RETRO-2026','CORR-2026')) AS dc
  FROM rides r
  WHERE r.deleted_at IS NULL
    AND r.start_time >= (p_from::timestamp AT TIME ZONE 'Europe/Brussels')
    AND r.start_time <  ((p_to + 1)::timestamp AT TIME ZONE 'Europe/Brussels')
), crew AS (
  SELECT id AS ride_id, user_id AS pid, 'chauffeur'::text AS rol FROM rides_p WHERE user_id IS NOT NULL
  UNION ALL SELECT id, second_driver_id, 'bijrijder' FROM rides_p WHERE second_driver_id IS NOT NULL
), sf AS (
  SELECT d.id, d.ride_id, d.is_installation, (d.is_unpacked = false) AS nu,
    CASE WHEN d.is_unpacked IS DISTINCT FROM false THEN NULL
      WHEN coalesce(d.not_unpacked_reason,'') ~* '(niet van toepassing|nvt|opgehaald|ophalen in de winkel|opgegalt|ophepakt|(van|in|uit) (de )?winkel|interventie|geen toestel|installeert|istalaci|instalaci|installatie uitgevoerd|tussenkader|geen delicaat|geopend|uitverpakt maar)' THEN 'nvt'
      WHEN coalesce(d.not_unpacked_reason,'') ~* '(buur|komşu|komsu|bıraktık|biraktik|bırakıldı|niet thuis|afwezig|eigenaar was niet)' THEN 'buren'
      WHEN coalesce(d.not_unpacked_reason,'') ~* '(klant|wenst|wil |wou|verpak|cadeau|cadeu|kadeu|kado|verbouw|renovatie|bouw|verhuis|transport|verplaats|bedrijf|export|buitenland|maroc|boot|inşa|insa|kocas|açma|açtır|istemedi|şyer|syer|sipari|man doet|zelf)' THEN 'klant'
      ELSE 'andere' END AS cat,
    nullif(trim(d.not_unpacked_reason),'') AS reden,
    (d.status='deviation' OR coalesce(d.is_deviation,false) OR EXISTS (SELECT 1 FROM stop_deviations sd WHERE sd.delivery_stop_id=d.id)) AS afw,
    (d.status='pending' AND r.end_time IS NOT NULL AND NOT r.dc) AS pend,
    d.rating_delivery, r.start_time, r.ride_number, d.stop_number, d.customer_name, d.city
  FROM delivery_stops d JOIN rides_p r ON r.id=d.ride_id WHERE r.ride_type <> 'click_collect'
), pr AS (
  SELECT id, ride_type, dc, start_time, ride_number, user_id, second_driver_id,
    (end_time IS NOT NULL AND NOT dc AND ((ride_type<>'click_collect' AND eind='20:00:00') OR (ride_type='click_collect' AND eind='16:30:00'))) AS auto_dicht,
    closing_started_by IS NOT NULL AS begonnen, end_time IS NULL AS open
  FROM rides_p
), kl AS (
  SELECT dz.id, dz.created_at, dz.status, dz.title, dz.customer_name, dz.driver_id, dz.second_driver_id, dz.second_driver_name, r.start_time AS ritdatum, r.ride_number,
    (r.start_time >= (p_from::timestamp AT TIME ZONE 'Europe/Brussels') AND r.start_time < ((p_to + 1)::timestamp AT TIME ZONE 'Europe/Brussels')) AS rit_in_periode
  FROM dossiers dz LEFT JOIN rides r ON r.id=dz.ride_id
  WHERE dz.dossier_type='klacht' AND (
     (r.start_time >= (p_from::timestamp AT TIME ZONE 'Europe/Brussels') AND r.start_time < ((p_to + 1)::timestamp AT TIME ZONE 'Europe/Brussels'))
     OR (dz.created_at >= (p_from::timestamp AT TIME ZONE 'Europe/Brussels') AND dz.created_at < ((p_to + 1)::timestamp AT TIME ZONE 'Europe/Brussels')))
), klp AS (
  SELECT k.id, x.pid, k.rit_in_periode FROM kl k CROSS JOIN LATERAL (VALUES (k.driver_id),(k.second_driver_id)) x(pid) WHERE x.pid IS NOT NULL
), pids AS (
  SELECT pid FROM crew UNION SELECT pid FROM klp
)
SELECT json_build_object(
 'van', p_from, 'tot', p_to,
 'totaal', (SELECT json_build_object('ritten',count(*),'ic',count(*) FILTER (WHERE ride_type<>'click_collect'),'cc',count(*) FILTER (WHERE ride_type='click_collect'),
     'eigen',count(*) FILTER (WHERE NOT dc),'auto',count(*) FILTER (WHERE auto_dicht),'auto_begonnen',count(*) FILTER (WHERE auto_dicht AND begonnen),'open',count(*) FILTER (WHERE open)) FROM pr),
 'stops', (SELECT json_build_object('stops',count(*),'inst',count(*) FILTER (WHERE is_installation),'afzet',count(*) FILTER (WHERE NOT is_installation),
     'nu',count(*) FILTER (WHERE nu),'nu_klant',count(*) FILTER (WHERE cat='klant'),'nu_buren',count(*) FILTER (WHERE cat='buren'),'nu_nvt',count(*) FILTER (WHERE cat='nvt'),'nu_andere',count(*) FILTER (WHERE cat='andere'),
     'afw',count(*) FILTER (WHERE afw),'pend',count(*) FILTER (WHERE pend),'rating',round(avg(rating_delivery),2),'n_rating',count(rating_delivery)) FROM sf),
 'personen', (SELECT json_agg(x) FROM (
   SELECT p.full_name AS naam, pids.pid,
     (SELECT count(DISTINCT c.ride_id) FROM crew c WHERE c.pid=pids.pid AND c.rol='chauffeur') AS rc,
     (SELECT count(DISTINCT c.ride_id) FROM crew c WHERE c.pid=pids.pid AND c.rol='bijrijder') AS rb,
     (SELECT count(DISTINCT c.ride_id) FROM crew c JOIN pr ON pr.id=c.ride_id WHERE c.pid=pids.pid AND pr.ride_type='click_collect') AS cc,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid) AS stops,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid AND sf.is_installation) AS inst,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid AND NOT sf.is_installation) AS afzet,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid AND sf.nu) AS nu,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid AND sf.cat='klant') AS nu_klant,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid AND sf.cat='buren') AS nu_buren,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid AND sf.cat='nvt') AS nu_nvt,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid AND sf.cat='andere') AS nu_andere,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid AND sf.afw) AS afw,
     (SELECT count(*) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid AND sf.pend) AS pend,
     (SELECT count(DISTINCT c.ride_id) FROM crew c JOIN pr ON pr.id=c.ride_id WHERE c.pid=pids.pid AND c.rol='chauffeur' AND NOT pr.dc) AS rc_eigen,
     (SELECT count(DISTINCT c.ride_id) FROM crew c JOIN pr ON pr.id=c.ride_id WHERE c.pid=pids.pid AND c.rol='chauffeur' AND pr.auto_dicht) AS auto,
     (SELECT count(DISTINCT c.ride_id) FROM crew c JOIN pr ON pr.id=c.ride_id WHERE c.pid=pids.pid AND c.rol='chauffeur' AND pr.auto_dicht AND pr.begonnen) AS auto_begonnen,
     (SELECT round(avg(sf.rating_delivery),2) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid) AS rating,
     (SELECT count(sf.rating_delivery) FROM crew c JOIN sf ON sf.ride_id=c.ride_id WHERE c.pid=pids.pid) AS n_rating,
     (SELECT count(DISTINCT k.id) FROM klp k WHERE k.pid=pids.pid AND k.rit_in_periode) AS klachten,
     (SELECT count(DISTINCT k.id) FROM klp k WHERE k.pid=pids.pid AND NOT coalesce(k.rit_in_periode,false)) AS klachten_ouder
   FROM pids LEFT JOIN profiles p ON p.user_id=pids.pid) x),
 'niet_uitgepakt', (SELECT json_agg(x ORDER BY x.s) FROM (
   SELECT sf.start_time AS s, to_char(sf.start_time AT TIME ZONE 'Europe/Brussels','DD/MM') AS dag, sf.ride_number, sf.stop_number, sf.customer_name, sf.city, sf.cat, sf.reden,
     (SELECT string_agg(p.full_name, ' & ' ORDER BY c.rol DESC) FROM crew c JOIN profiles p ON p.user_id=c.pid WHERE c.ride_id=sf.ride_id) AS ploeg
   FROM sf WHERE sf.nu) x),
 'auto_ritten', (SELECT json_agg(x ORDER BY x.s) FROM (
   SELECT pr.start_time AS s, to_char(pr.start_time AT TIME ZONE 'Europe/Brussels','DD/MM') AS dag, pr.ride_number, pr.ride_type, p.full_name AS chauffeur, p2.full_name AS bijrijder, pr.begonnen
   FROM pr LEFT JOIN profiles p ON p.user_id=pr.user_id LEFT JOIN profiles p2 ON p2.user_id=pr.second_driver_id WHERE pr.auto_dicht) x),
 'pending_ritten', (SELECT json_agg(x ORDER BY x.s) FROM (
   SELECT min(sf.start_time) AS s, to_char(min(sf.start_time) AT TIME ZONE 'Europe/Brussels','DD/MM') AS dag, sf.ride_number, count(*) AS pending,
     (SELECT string_agg(p.full_name, ' & ' ORDER BY c.rol DESC) FROM crew c JOIN profiles p ON p.user_id=c.pid WHERE c.ride_id=sf.ride_id) AS ploeg
   FROM sf WHERE sf.pend GROUP BY sf.ride_id, sf.ride_number) x),
 'klachten', (SELECT json_agg(x ORDER BY x.created_at) FROM (
   SELECT k.created_at, to_char(k.created_at AT TIME ZONE 'Europe/Brussels','DD/MM') AS ontvangen, to_char(k.ritdatum AT TIME ZONE 'Europe/Brussels','DD/MM/YYYY') AS ritdag, k.ride_number, k.status, k.customer_name, left(k.title,90) AS titel, k.rit_in_periode,
     p.full_name AS chauffeur, coalesce(p2.full_name, k.second_driver_name) AS bijrijder
   FROM kl k LEFT JOIN profiles p ON p.user_id=k.driver_id LEFT JOIN profiles p2 ON p2.user_id=k.second_driver_id) x),
 'weken', (SELECT json_agg(x ORDER BY x.wk) FROM (
   SELECT (date_trunc('week', (pr.start_time AT TIME ZONE 'Europe/Brussels') + interval '1 day')::date - 1) AS wk, count(DISTINCT pr.id) AS ritten,
     count(sf.id) AS stops, count(sf.id) FILTER (WHERE NOT sf.is_installation) AS afzet, count(sf.id) FILTER (WHERE sf.nu AND sf.cat<>'nvt') AS nu,
     count(DISTINCT pr.id) FILTER (WHERE pr.auto_dicht) AS auto
   FROM pr LEFT JOIN sf ON sf.ride_id=pr.id GROUP BY 1) x)
);
$fn$;
REVOKE ALL ON FUNCTION public.driver_stats(date, date) FROM PUBLIC, anon, authenticated;
