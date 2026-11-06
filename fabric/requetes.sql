-- Requêtes pour le point de terminaison SQL du Lakehouse (données fictives).

-- 1. Volume, refus et escalades par région
SELECT
    a.region,
    COUNT(*) AS questions,
    ROUND(AVG(CASE WHEN f.statut = 'refus' THEN 1.0 ELSE 0 END), 3) AS taux_refus,
    ROUND(AVG(CASE WHEN f.statut = 'escalade' THEN 1.0 ELSE 0 END), 3) AS taux_escalade
FROM fact_questions AS f
JOIN dim_agence AS a ON a.agence_id = f.agence_id
GROUP BY a.region
ORDER BY questions DESC;

-- 2. Thèmes les moins bien évalués
SELECT
    theme,
    COUNT(feedback) AS retours,
    ROUND(AVG(CASE WHEN feedback = 'utile' THEN 1.0 ELSE 0 END), 3) AS taux_utile
FROM fact_questions
WHERE feedback IS NOT NULL
GROUP BY theme
ORDER BY taux_utile ASC;

-- 3. Coût estimé et latence par mois et par langue
SELECT
    d.nom_mois,
    f.langue,
    COUNT(*) AS questions,
    ROUND(SUM(f.cout_estime_usd), 2) AS cout_estime_usd,
    ROUND(AVG(f.latence_ms) / 1000.0, 2) AS latence_moyenne_s
FROM fact_questions AS f
JOIN dim_date AS d ON d.date = f.date
GROUP BY d.nom_mois, f.langue
ORDER BY d.nom_mois, f.langue;
