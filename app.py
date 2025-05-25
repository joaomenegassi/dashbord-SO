# app.py

import streamlit as st
from model import get_process_details  # Importa a função para buscar detalhes de um processo específico
from view import display_main_layout   # Importa a função que constrói a interface principal
from streamlit_autorefresh import st_autorefresh  # Importa a função para auto-refresh da página
from controller import start_background_thread, system_data  # Importa o controlador de dados e a thread de background

# --- Configuração da Página do Streamlit ---
# Define o título da página, layout (largo), e estado inicial da barra lateral (expandida).
st.set_page_config(
    page_title="Dashboard de Monitoramento de Sistema",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Estilo CSS para Ocultar Elementos Padrão do Streamlit ---
# Define um bloco de CSS para remover o menu principal, rodapé e cabeçalho do Streamlit,
# e ajusta o padding do container principal para um visual mais limpo.
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.block-container {
    padding-top: 0px;
    padding-bottom: 0;
    margin-bottom: 20px;
}
header {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True) # Aplica o CSS à página

# --- Configuração do Auto-Refresh da Interface ---
REFRESH_INTERVAL_MS = 3000  # Define o intervalo de atualização da interface em milissegundos (3 segundos)
# Inicia o componente de auto-refresh do Streamlit para atualizar a UI periodicamente.
st_autorefresh(interval=REFRESH_INTERVAL_MS, key="ui_refresh_key")

# --- Inicialização do Estado da Sessão ---
# Garante que 'num_processes_to_show' (número de processos a exibir na tabela)
# seja inicializado no estado da sessão se ainda não existir. O valor padrão é 10.
if 'num_processes_to_show' not in st.session_state:
    st.session_state.num_processes_to_show = 10  #

# --- Obtenção Inicial dos Dados do Sistema ---
# Busca um "snapshot" atual das informações globais e da lista de processos
# do objeto system_data (gerenciado pelo controller).
global_info, processes = system_data.get_snapshot() #

# --- Lógica de Fallback para Informações Globais (Segurança) ---
# Define um dicionário com chaves esperadas para 'global_info' e seus valores padrão.
# Isso garante que a interface não quebre caso alguma chave esteja faltando nos dados recebidos.
default_global_info_keys = {
    "CPU (%)": 0.0, "CPU ocioso (%)": 0.0,
    "Memória Usada (KB)": 0,
    "Memória (%)": 0.0,
    "Memória Livre (%)": 0.0,
    "Swap Total (KB)": 0,
    "Swap Usada (KB)": 0,
    "Swap Usada (%)": 0.0,
    "Total de Processos": 0, "Total de Threads": 0,
    "Leitura Disco (B/s)": 0.0,
    "Escrita Disco (B/s)": 0.0
}

# Se 'global_info' foi obtido com sucesso, verifica e adiciona chaves faltantes com valores padrão.
if global_info: #
    for key, default_value in default_global_info_keys.items(): #
        global_info.setdefault(key, default_value) #
else:
    # Se 'global_info' estiver vazio ou None, usa a cópia dos valores padrão.
    global_info = default_global_info_keys.copy() #


# --- Renderização da Interface Principal ---
# Chama a função 'display_main_layout' do 'view.py' para construir e exibir a interface.
# Passa os dados globais, a lista de processos, a função para obter detalhes de um processo,
# e o número atual de processos a serem exibidos.
# Retorna o valor (string) inserido pelo usuário no campo "Quantos processos visualizar?".
num_processes_input_str_from_view = display_main_layout(
    global_info_data=global_info,
    processes_data=processes,
    get_process_details_func=get_process_details,
    current_num_processes_value=st.session_state.num_processes_to_show #
)

# --- Processamento da Entrada do Usuário para o Número de Processos ---
try:
    # Tenta converter a entrada do usuário para um número inteiro.
    new_num_processes_limit = int(num_processes_input_str_from_view) #
    # Validação: o número de processos deve ser pelo menos 1.
    if new_num_processes_limit < 1: #
        # Se o valor inválido for diferente do valor atual, exibe um aviso.
        if new_num_processes_limit != st.session_state.num_processes_to_show: #
             st.sidebar.warning(f"O número de processos deve ser pelo menos 1. Mantendo {st.session_state.num_processes_to_show}.") #
        # Mantém o valor anterior se a entrada for inválida.
        new_num_processes_limit = st.session_state.num_processes_to_show #

except ValueError:
    # Se a conversão para inteiro falhar (ex: usuário digitou texto).
    new_num_processes_limit = st.session_state.num_processes_to_show #
    # Se a string de entrada for diferente da string do valor atual (evita warning em refresh sem mudança), exibe aviso.
    if num_processes_input_str_from_view != str(st.session_state.num_processes_to_show): #
        st.sidebar.warning(f"Entrada '{num_processes_input_str_from_view}' inválida para número de processos. Mantendo {st.session_state.num_processes_to_show}.") #

# --- Atualização do Limite de Processos e Reinício da Coleta/Interface ---
# Verifica se o novo limite de processos é diferente do valor atual no estado da sessão.
if new_num_processes_limit != st.session_state.num_processes_to_show: #
    # Se for diferente, atualiza o valor no estado da sessão.
    st.session_state.num_processes_to_show = new_num_processes_limit #
    # (Re)inicia a thread de coleta de dados em background com o novo limite.
    # O intervalo de coleta de dados da thread é fixo em 2 segundos aqui.
    start_background_thread(interval=2, limit=st.session_state.num_processes_to_show) #
    # Força um re-run da aplicação Streamlit para atualizar a interface com o novo limite.
    st.rerun() #
else:
    # Se o limite não mudou, ainda chama 'start_background_thread'.
    # Isso garante que a thread de coleta de dados seja iniciada na primeira execução
    # e que o 'limit' no 'system_data' (controller) esteja sempre sincronizado,
    # mesmo que o número de processos não mude, mas a thread precise ser iniciada.
    # A lógica interna de 'start_background_thread' impede múltiplas threads.
    start_background_thread(interval=2, limit=st.session_state.num_processes_to_show) #