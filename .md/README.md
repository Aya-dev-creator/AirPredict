# AirWatch - Système de Surveillance de la Qualité de l'Air (PFE)

Application web **100% Server-Side Rendered (SSR)** conçue pour la surveillance de la qualité de l'air en temps réel, optimisée pour un déploiement léger (Raspberry Pi ou serveur).

## 🚀 Architecture "Zero-JS" (No JavaScript)
Pour garantir une stabilité maximale et une consommation de ressources minimale sur Raspberry Pi, le projet a été entièrement refactorisé pour fonctionner **sans aucun script JavaScript côté client**.
- **Performance** : Chargement instantané des pages, même sur des connexions lentes.
- **Sécurité** : Réduction de la surface d'attaque en éliminant les scripts tiers.
- **Accessibilité** : Fonctionne sur tous les navigateurs, même les plus anciens ou ceux sans support JS.

---

## 📋 Fonctionnalités Principales

### 1. Tableau de Bord (Dashboard)
- **Données en Temps Réel** : Affichage de l'indice de qualité de l'air (AQI) via une interface CSS moderne.
- **Météo Intégrée** : Données complètes via l'API OpenWeatherMap (Température, Humidité, Vent, etc.).
- **Statistiques sur 24h** : Calcul automatique des moyennes, minimums et maximums de pollution.
- **Prévisions sur 5 jours** : Anticipez les changements environnementaux.

### 2. Carte GPS Statique
- **Visualisation sans JS** : Utilisation d'une intégration OpenStreetMap par Iframe.
- **Géolocalisation des Capteurs** : Affiche la position réelle du système.
- **Mode Secours (Fallback)** : Si le signal GPS est absent, la carte utilise automatiquement la position fournie par l'API Météo.


### 3. Analyses & Prédictions
- **Analytique avancée** : Rapports détaillés sur l'historique des mesures générés en Python.
- **Prédictions par Machine Learning** : Modèle prédictif intégré pour estimer l'évolution de la qualité de l'air.
- **Données NASA** : Intégration des événements environnementaux mondiaux.

### 5. Design Premium & Personnalisation
- **Thème Sombre/Clair** : Basculez entre les modes via un switch ergonomique.
- **Persistance du Thème** : Votre choix de thème est enregistré côté serveur (Session Flask).
- **Interface Responsive** : Design optimisé pour Mobile, Tablette et Desktop.

---

## 🛠️ Installation Technique

### Prérequis
- Python 3.9+
- Pip (Gestionnaire de paquets)

### Lancement Rapide
```bash
# Entrer dans le dossier du projet
cd versel

# Créer l'environnement virtuel
python -m venv .venv
source .venv/bin/activate  # Sur Linux/Pi
# .venv\Scripts\activate   # Sur Windows

# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur
python web_server.py
```

### Configuration
Éditez le fichier `.env` pour configurer vos clés API :
- `OPENWEATHER_API_KEY` : Pour la météo.

---

## 📂 Structure du Projet
- `web_server.py` : Cœur de l'application (Flask).
- `database.py` : Gestion de la base de données SQLite.
- `ml_model.py` : Modèle de prédiction Intelligence Artificielle.
- `openweather_data_provider.py` : Récupération météo et qualité de l'air (OpenWeatherMap).
- `templates/` : Pages HTML (SSR avec Jinja2).
- `static/css/` : Design et thèmes (Sans JS).

---

## 💡 Remarques pour le PFE
Ce projet démontre une approche **minimaliste et robuste** du Web moderne, privilégiant le traitement côté serveur pour alléger la charge du client et assurer une fiabilité exemplaire en environnement IoT.