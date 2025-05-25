# Makefile simples para rodar o Dashboard

# Instala as bibliotecas que o projeto precisa
install:
	pip install -r requirements.txt

# Roda a aplicação principal com Streamlit
run:
	streamlit run app.py

.PHONY: install run