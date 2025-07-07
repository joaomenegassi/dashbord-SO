.PHONY: all run install clean update-requirements

# Variável para o interpretador Python, útil para ambientes virtuais
PYTHON = python3

# Nome do arquivo principal do Streamlit
APP_FILE = app.py

# Diretório para o ambiente virtual
VENV_DIR = venv

all: install run

# Instala as dependências do projeto em um ambiente virtual.
install: $(VENV_DIR)
	@echo "Instalando dependências..."
	@./$(VENV_DIR)/bin/$(PYTHON) -m pip install -r requirements.txt
	@echo "Instalação concluída."

$(VENV_DIR):
	@echo "Criando ambiente virtual..."
	@$(PYTHON) -m venv $(VENV_DIR)
	@echo "Ambiente virtual criado."

# Atualiza o arquivo requirements.txt com as dependências atualmente instaladas no venv.
update-requirements: $(VENV_DIR)
	@echo "Atualizando requirements.txt com as dependências do ambiente virtual..."
	@./$(VENV_DIR)/bin/$(PYTHON) -m pip freeze > requirements.txt
	@echo "requirements.txt atualizado."


# Executa a aplicação Streamlit.
run: install
	@echo "Iniciando o Dashboard de Monitoramento de Sistema..."
	@./$(VENV_DIR)/bin/streamlit run $(APP_FILE)

# Limpa o ambiente virtual e os arquivos de cache.
clean:
	@echo "Limpando ambiente virtual e caches..."
	@rm -rf $(VENV_DIR)
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@rm -f requirements.txt # Remove o requirements.txt também ao limpar
	@echo "Limpeza concluída."