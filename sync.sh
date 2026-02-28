#!/bin/bash

# Entra na pasta do projeto
cd /home/valeverdepm/plataforma_policial

# Adiciona todas as alterações que você fez no editor
git add .

# Cria um commit com a data e hora atual
git commit -m "Auto-sync: $(date +'%d/%m/%Y %H:%M:%S')"

# Envia para o GitHub (Repositório sentryvv)
git push origin main