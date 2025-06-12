import streamlit as st
from model import get_process_details  # Importa a função para buscar detalhes de um processo específico do arquivo model.py.
from view import display_main_layout   # Importa a função que constrói a interface principal do arquivo view.py.
from streamlit_autorefresh import st_autorefresh  # Importa a função para auto-refresh da página, permitindo atualizações automáticas da interface.
from controller import start_background_thread, system_data  # Importa a função para iniciar a thread de coleta de dados e o objeto que armazena os dados do sistema do controller.py.

# --- Configuração da Página do Streamlit ---
# Define o título da página que aparece na aba do navegador, o layout como "wide" para ocupar mais espaço horizontal,
# e o estado inicial da barra lateral como "expanded" (expandida).
st.set_page_config(
    page_title="Dashboard de Monitoramento de Sistema",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Estilo CSS para Ocultar Elementos Padrão do Streamlit ---
# Define um bloco de CSS customizado para modificar a aparência da página.
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
st.markdown(hide_streamlit_style, unsafe_allow_html=True) # Aplica o CSS à página.

# --- Configuração do Auto-Refresh da Interface ---
REFRESH_INTERVAL_MS = 3000  # Define o intervalo de atualização da interface em milissegundos (3000 ms = 3 segundos).
# Inicia o componente de auto-refresh do Streamlit.
st_autorefresh(interval=REFRESH_INTERVAL_MS, key="ui_refresh_key")

# --- Inicialização do Estado da Sessão ---
# O estado da sessão (`st.session_state`) é usado para armazenar variáveis que persistem entre re-execuções do script (como em atualizações).
# Garante que 'num_processes_to_show' (número de processos a exibir na tabela)
# seja inicializado no estado da sessão se ainda não existir. O valor padrão é 10.
if 'num_processes_to_show' not in st.session_state: # Verifica se a chave 'num_processes_to_show' já existe no estado da sessão.
    st.session_state.num_processes_to_show = 10  # Se não existir, inicializa com o valor 10.

# --- Obtenção Inicial dos Dados do Sistema ---
# Busca um "snapshot" (uma cópia instantânea) atual das informações globais e da lista de processos
# do objeto `system_data` (que é gerenciado pelo controller.py e atualizado em background).
global_info, processes = system_data.get_snapshot() # Chama o método get_snapshot() para obter os dados mais recentes.

# --- Lógica de Fallback para Informações Globais ---
# Define um dicionário com chaves esperadas para 'global_info' e seus valores padrão.
# Isso garante que a interface não quebre caso alguma chave esteja faltando nos dados recebidos do `system_data`,
default_global_info_keys = {
    "CPU (%)": 0.0, "CPU ocioso (%)": 0.0,
    "Memória Usada (KB)": 0,
    "Memória (%)": 0.0,
    "Memória Livre (%)": 0.0,
    "Total de Processos": 0, "Total de Threads": 0,
    "Leitura Disco (B/s)": 0.0,
    "Escrita Disco (B/s)": 0.0
}

# Se 'global_info' foi obtido com sucesso,
# itera sobre as chaves padrão e garante que cada uma exista em `global_info`.
# Se uma chave não existir, ela é adicionada com seu valor padrão.
if global_info:
    for key, default_value in default_global_info_keys.items(): # Itera sobre o dicionário de chaves e valores padrão.
        global_info.setdefault(key, default_value) # Adiciona a chave com o valor padrão se ela não existir em global_info.
else:
    # Se 'global_info' estiver vazio ou None (ex: primeira execução ou erro na coleta),
    # usa uma cópia dos valores padrão para evitar erros na interface.
    global_info = default_global_info_keys.copy()


# --- Renderização da Interface Principal ---
# A função `display_main_layout` retorna o valor (string) inserido pelo usuário no campo "Quantos processos visualizar?".
num_processes_input_str_from_view = display_main_layout(
    global_info_data=global_info,
    processes_data=processes,
    get_process_details_func=get_process_details,
    current_num_processes_value=st.session_state.num_processes_to_show # Passa o valor atual do estado da sessão para a view.
)

# --- Processamento da Entrada do Usuário para o Número de Processos ---
try:
    # Tenta converter a entrada do usuário (que é uma string) para um número inteiro.
    new_num_processes_limit = int(num_processes_input_str_from_view) # Converte a string para inteiro.
    # Validação: o número de processos a ser exibido deve ser pelo menos 1.
    if new_num_processes_limit < 1: # Verifica se o número é menor que 1.
        # Se o valor inválido (ex: 0 ou negativo) for diferente do valor atualmente em uso, exibe um aviso na barra lateral.
        if new_num_processes_limit != st.session_state.num_processes_to_show: # Evita warnings repetidos se o valor inválido não mudou.
             st.sidebar.warning(f"O número de processos deve ser pelo menos 1. Mantendo {st.session_state.num_processes_to_show}.")
        # Mantém o valor anterior (do estado da sessão) se a entrada for inválida.
        new_num_processes_limit = st.session_state.num_processes_to_show

except ValueError:
    # Se a conversão para inteiro falhar (ex: usuário digitou texto como "abc")
    # mantém o valor anterior do estado da sessão.
    new_num_processes_limit = st.session_state.num_processes_to_show
    # Se a string de entrada for diferente da representação string do valor atual
    if num_processes_input_str_from_view != str(st.session_state.num_processes_to_show):
        st.sidebar.warning(f"Entrada '{num_processes_input_str_from_view}' inválida para número de processos. Mantendo {st.session_state.num_processes_to_show}.")

# --- Atualização do Limite de Processos e Reinício da Coleta/Interface ---
# Verifica se o novo limite de processos (após validação) é diferente do valor atual no estado da sessão.
if new_num_processes_limit != st.session_state.num_processes_to_show:
    # Se for diferente, atualiza o valor no estado da sessão.
    st.session_state.num_processes_to_show = new_num_processes_limit
    # (Re)inicia a thread de coleta de dados em background.
    # Passa o intervalo de coleta (fixo em 2 segundos aqui para a thread de dados) e o novo limite de processos.
    # A função `start_background_thread` no controller é responsável por gerenciar a thread (iniciar ou atualizar seu limite).
    start_background_thread(interval=2, limit=st.session_state.num_processes_to_show) # Reinicia/atualiza a thread com o novo limite.
    # Força um re-run da aplicação Streamlit. Isso faz com que o script app.py seja executado novamente do início,
    # o que atualizará a interface com o novo limite de processos.
    st.rerun()
else:
    # Se o limite não mudou, ainda chama 'start_background_thread'.
    # A thread de coleta de dados seja iniciada na primeira execução da aplicação.
    # O 'limit' dentro do objeto `system_data` (no controller) esteja sempre sincronizado com `st.session_state.num_processes_to_show`,
    # A lógica interna de 'start_background_thread' (uso da flag `_thread_started`) impede a criação de múltiplas threads.
    start_background_thread(interval=2, limit=st.session_state.num_processes_to_show) # Garante que a thread esteja rodando e com o limite correto.