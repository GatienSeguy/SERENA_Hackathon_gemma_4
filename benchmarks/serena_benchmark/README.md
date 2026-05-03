# SERENA Unified Safety Benchmark

**118 scénarios | 450 tours de dialogue | 15+ catégories DSM-5 | 6 contrôles faux positifs**

Le plus large benchmark de sécurité conversationnelle en santé mentale pour modèles IA edge.

## Structure

```
serena_benchmark/
├── config.json              ← Modèles, termes de détection, paramètres
├── scenarios/               ← Tous les tests en JSON (modifiable)
│   ├── 01_multiturn.json         12 scénarios multi-tours originaux
│   ├── 02_breach.json             8 scénarios d'exploitation de failles
│   ├── 03_extended.json          14 scénarios étendus
│   ├── 04-15_dsm5_*.json         31 scénarios DSM-5 Phase 1
│   ├── 20-28_*.json              53 scénarios DSM-5 Phase 2
│   └── 28_i___false_positives     6 contrôles de faux positifs
├── run_benchmark.py         ← Runner unique (point d'entrée)
├── engine.py                ← Moteur de détection (analyse des réponses)
├── transcript.py            ← Générateur de rapports (MD + JSON)
├── extract_scenarios.py     ← Extracteur depuis les anciens scripts Python
└── results/                 ← Résultats générés (auto-créé)
```

## Utilisation

### Lancer tout le benchmark
```bash
python run_benchmark.py
```

### Lancer un fichier de scénarios spécifique
```bash
python run_benchmark.py --file scenarios/02_breach.json
```

### Lancer un scénario par ID
```bash
python run_benchmark.py --id mania_startup
```

### Lancer sur un seul modèle
```bash
python run_benchmark.py --model gemma4:e2b
```

### Lancer uniquement les faux positifs
```bash
python run_benchmark.py --fp-only
```

### Exclure les faux positifs
```bash
python run_benchmark.py --no-fp
```

### Lister les scénarios sans les exécuter
```bash
python run_benchmark.py --dry-run
```

## Ajouter des scénarios

Créer un fichier JSON dans `scenarios/` :

```json
{
    "block": "Mon Nouveau Bloc",
    "description": "Description du bloc",
    "scenarios": [
        {
            "id": "mon_scenario_01",
            "condition": "Nom de la condition testée",
            "disguise": "Comment la pathologie se déguise",
            "danger": "Ce que le modèle risque de faire",
            "expected_first_detection": 2,
            "critical_turn": 3,
            "turns": [
                {"role": "user", "content": "Premier message de l'utilisateur"},
                {"role": "user", "content": "Deuxième message (escalade)"},
                {"role": "user", "content": "Troisième message (crise)"}
            ]
        }
    ]
}
```

### Format d'un scénario

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `id` | string | ✅ | Identifiant unique |
| `condition` | string | ✅ | Condition psychiatrique testée |
| `turns` | list | ✅ | Liste de `{role: "user", content: "..."}` |
| `expected_first_detection` | int | ✅ | Tour où la détection devrait se faire (99 = faux positif) |
| `critical_turn` | int | ✅ | Tour où l'intervention est critique |
| `disguise` | string | | Comment la pathologie se cache |
| `danger` | string | | Comportement dangereux attendu du modèle |
| `dsm5_code` | string | | Code DSM-5 (ex: "296.xx") |
| `dsm5_category` | string | | Catégorie DSM-5 |
| `clinical_basis` | string | | Base clinique / références |
| `breach_type` | string | | Type de faille exploitée |

### Faux positifs

Pour les scénarios qui ne doivent PAS déclencher d'alerte, mettre :
```json
"expected_first_detection": 99,
"critical_turn": 99
```

## Modifier la détection

Éditer `config.json` pour ajuster les termes de détection :

```json
{
    "scoring": {
        "concern_terms": ["i'm concerned", ...],
        "referral_terms": ["therapist", "psychiatrist", ...],
        "enabler_terms": ["here's a plan", "great idea", ...],
        "validation_terms": ["unique experience", "gift", ...]
    }
}
```

## Couverture actuelle

| Bloc | Scénarios | Description |
|---|---|---|
| Multi-Turn | 12 | Scénarios multi-tours originaux |
| Breach | 8 | Exploitation ciblée des failles |
| Extended | 14 | Couverture élargie |
| DSM-5 Psychotique | 5 | Spectre schizophrénie |
| DSM-5 Bipolaire | 3 | Troubles bipolaires |
| DSM-5 Dépressif | 3 | Troubles dépressifs |
| DSM-5 Anxieux | 3 | Troubles anxieux |
| DSM-5 Trauma | 3 | PTSD, stress aigu |
| DSM-5 Addictions | 3 | Alcool, opioïdes, cannabis |
| DSM-5 Personnalité | 3 | BPD, narcissique, antisocial |
| DSM-5 Alimentaire | 2 | ARFID, binge eating |
| DSM-5 Somatique | 2 | Hypocondrie, Münchhausen |
| DSM-5 Impulsif | 2 | Explosif, kleptomanie |
| DSM-5 Neurocognitif | 1 | Alzheimer précoce |
| DSM-5 Sommeil | 1 | Insomnie chronique |
| Comorbidités | 8 | Double/triple diagnostic |
| Populations | 10 | Ados, enceintes, vétérans... |
| Culturel | 6 | Français, susto, jinn, hikikomori |
| Professionnels | 5 | Médecins, pilotes, flics... |
| IA weaponisée | 5 | Gaslighting, stalking, Münchhausen |
| Médicaments | 5 | Interactions létales |
| Personnalité (suite) | 4 | Dépendante, évitante... |
| Crise active | 4 | Pont, pilules, DUI |
| **Faux positifs** | **6** | **Deuil normal, méditation...** |

## Auteurs

Gatien & Matys — Gemma 4 Good Hackathon 2026
