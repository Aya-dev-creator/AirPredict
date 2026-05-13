# ☁️ Guide Cloudflare Tunnel pour Raspberry Pi

Ce guide explique comment exposer votre application **AirWatch** sur Internet de manière sécurisée sans ouvrir de ports sur votre routeur.

## 1. Installation de Cloudflared
Sur votre Raspberry Pi, exécutez les commandes suivantes :

```bash
# Télécharger le binaire pour l'architecture ARM (Raspberry Pi 4)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o cloudflared

# Rendre le fichier exécutable
chmod +x cloudflared

# Déplacer vers le dossier des binaires
sudo mv cloudflared /usr/local/bin/
```

## 2. Authentification
Connectez-vous à votre compte Cloudflare :

```bash
cloudflared tunnel login
```
*Un lien s'affichera. Copiez-le dans votre navigateur et sélectionnez le domaine que vous souhaitez utiliser.*

## 3. Création du Tunnel
Créez un tunnel nommé `airwatch-pfe` :

```bash
cloudflared tunnel create airwatch-pfe
```
*Notez l'ID du tunnel généré (ex: `12345678-1234-1234-1234-1234567890ab`).*

## 4. Configuration
Créez un fichier de configuration dans le dossier Cloudflare :

```bash
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```

Ajoutez le contenu suivant (remplacez l'ID et votre domaine) :
```yaml
tunnel: 12345678-1234-1234-1234-1234567890ab
credentials-file: /home/pi/.cloudflared/12345678-1234-1234-1234-1234567890ab.json

ingress:
  - hostname: airwatch.votre-domaine.com
    service: http://localhost:5000
  - service: http_status:404
```

## 5. Liaison DNS
Créez l'enregistrement DNS pour votre domaine :

```bash
cloudflared tunnel route dns airwatch-pfe airwatch.votre-domaine.com
```

## 6. Lancement Automatique (Service)
Pour que le tunnel se lance au démarrage du Pi :

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

---
✅ **Félicitations !** Votre application est maintenant accessible via `https://airwatch.votre-domaine.com` avec un certificat SSL gratuit et une protection DDoS.
