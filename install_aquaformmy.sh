#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}[INFO] Iniciando instalação do Aquaformmy...${NC}"

echo -e "${BLUE}[INFO] Limpando builds anteriores...${NC}"
rm -rf ./build ./dist *.spec

if [ ! -d "venv" ]; then
    echo -e "${RED}[ERRO] Ambiente virtual não encontrado! Crie um ambiente virtual primeiro:${NC}"
    echo -e "${BLUE}python -m venv venv${NC}"
    exit 1
fi

echo -e "${BLUE}[INFO] Ativando ambiente virtual...${NC}"
source venv/Scripts/Activate || source venv/bin/Activate

if ! command -v pyinstaller &> /dev/null; then
    echo -e "${BLUE}[INFO] Instalando pyinstaller no ambiente virtual...${NC}"
    pip install pyinstaller
fi

echo -e "${BLUE}[INFO] Gerando executável com PyInstaller...${NC}"
pyinstaller --onefile --name aquaformmy aquaformmy.py

if [ ! -f "./dist/aquaformmy.exe" ]; then
    echo -e "${RED}[ERRO] Falha ao gerar o executável!${NC}"
    deactivate
    exit 1
fi

echo -e "${BLUE}[INFO] Movendo executável para System32...${NC}"
if [ -w "/c/Windows/System32" ]; then
    mv ./dist/aquaformmy.exe ./
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[SUCESSO] Coloque o .exe no path do seu PC!${NC}"
    else
        echo -e "${RED}[ERRO] Falha ao mover o executável para System32!${NC}"
        deactivate
        exit 1
    fi
else
    echo -e "${RED}[ERRO] Sem permissão para escrever em System32. Execute o script como administrador!${NC}"
    deactivate
    exit 1
fi

deactivate

echo -e "${BLUE}[INFO] Limpando builds anteriores...${NC}"
rm -rf ./build ./dist *.spec
echo -e "${GREEN}[SUCESSO] Limpando builds anteriores...${NC}"

echo -e "${GREEN}[SUCESSO] Instalação do Aquaformmy concluída com sucesso!${NC}"