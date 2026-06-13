#!/usr/bin/env bash
# Installe ffmpeg + les dépendances Python
apt-get update && apt-get install -y ffmpeg
pip install -r requirements.txt
