# 🎵 Discord Music Bot

Bot Discord musique avec panel de contrôle, file d'attente et commandes slash.

---

## 📁 Fichiers

| Fichier | Rôle |
|--------|------|
| `bot.py` | Code principal du bot |
| `requirements.txt` | Dépendances Python |
| `render.yaml` | Config de déploiement Render |
| `build.sh` | Script de build (installe ffmpeg) |

---

## 🚀 Déploiement sur Render

### 1. Mets le projet sur GitHub
- Crée un repo sur [github.com](https://github.com)
- Upload tous ces fichiers dedans

### 2. Crée un service sur Render
- Va sur [render.com](https://render.com) → **New → Web Service**
- Connecte ton repo GitHub
- Configure :

| Champ | Valeur |
|-------|--------|
| Environment | `Python` |
| Build Command | `apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt` |
| Start Command | `python bot.py` |

### 3. Ajoute ton token Discord
- Dans Render → onglet **Environment**
- Ajoute une variable : `DISCORD_TOKEN` = `ton-token-ici`

### 4. Anti-sleep avec UptimeRobot
- Va sur [uptimerobot.com](https://uptimerobot.com)
- Crée un monitor **HTTP** vers l'URL de ton service Render
- Intervalle : **5 minutes**

---

## 🎮 Commandes

| Commande | Description |
|----------|-------------|
| `/play <recherche>` | Jouer une musique YouTube |
| `/skip` | Passer à la suivante |
| `/stop` | Arrêter et vider la file |
| `/pause` | Mettre en pause |
| `/resume` | Reprendre |
| `/queue` | Voir la file d'attente |
| `/join` | Rejoindre le salon vocal |
| `/disconnect` | Déconnecter le bot |
| `/ping` | Tester la latence |
| `/kick` | Expulser un membre (modérateurs) |
| `/ban` | Bannir un membre (modérateurs) |

---

## ⚠️ Important

Ne mets **jamais** ton token directement dans le code.
Utilise toujours la variable d'environnement `DISCORD_TOKEN`.
