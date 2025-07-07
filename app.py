import streamlit as st # Importa a biblioteca Streamlit para construir a interface web.
from model_system import get_process_details # Importa a função para obter detalhes de um processo do seu módulo 'model_system'.
from view import display_main_layout # Importa a função principal de exibição da sua camada 'view'.
from streamlit_autorefresh import st_autorefresh # Importa a função para auto-atualização do Streamlit.
from controller import start_background_thread, system_data # Importa as funções para iniciar a thread e o objeto de dados do seu módulo 'controller'.

# Configurações iniciais da página Streamlit para otimizar a visualização.
st.set_page_config(
    page_title="Dashboard de Monitoramento de Sistema",
    layout="wide", # Usa a largura total da página.
    initial_sidebar_state="expanded"
)

# Estilo CSS customizado para esconder elementos padrão do Streamlit (cabeçalho, rodapé, menu principal).
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
st.markdown(hide_streamlit_style, unsafe_allow_html=True) # Aplica o CSS.

REFRESH_INTERVAL_MS = 3000 # Define o intervalo de auto-atualização da interface em milissegundos (3 segundos).
st_autorefresh(interval=REFRESH_INTERVAL_MS, key="ui_refresh_key") # Ativa a auto-atualização do Streamlit.

# Inicializa as variáveis de estado da sessão do Streamlit, que persistem entre as atualizações.
if 'num_processes_to_show' not in st.session_state:
    st.session_state.num_processes_to_show = 10 # Define o número padrão de processos a serem exibidos.
if 'current_path' not in st.session_state:
    st.session_state.current_path = "/" # Define o caminho inicial para a navegação no sistema de arquivos.

# Obtém um snapshot dos dados atuais do sistema do controller.
# Esta é a principal fonte de dados para a interface.
global_info, processes, filesystem_info, directory_contents, current_path_from_controller = system_data.get_snapshot()

# Sincroniza o caminho atual no estado da sessão com o caminho gerenciado pelo controller.
if st.session_state.current_path != current_path_from_controller:
    st.session_state.current_path = current_path_from_controller

# Garante que todas as chaves de informações globais essenciais estejam presentes, mesmo que vazias.
default_global_info_keys = {
    "CPU (%)": 0.0, "CPU ocioso (%)": 0.0,
    "Memória Usada (KB)": 0,
    "Memória (%)": 0.0,
    "Memória Livre (%)": 0.0,
    "Total de Processos": 0, "Total de Threads": 0,
    "Leitura Disco (B/s)": 0.0,
    "Escrita Disco (B/s)": 0.0
}
if global_info:
    for key, default_value in default_global_info_keys.items():
        global_info.setdefault(key, default_value)
else:
    global_info = default_global_info_keys.copy()

# Chama a função principal da camada de visualização (view) para renderizar o layout do dashboard.
# Passa os dados coletados e as funções de interação.
num_processes_input_str_from_view = display_main_layout(
    global_info_data=global_info,
    processes_data=processes,
    get_process_details_func=get_process_details,
    current_num_processes_value=st.session_state.num_processes_to_show,
    filesystem_data=filesystem_info,
    directory_contents_data=directory_contents,
    current_path=st.session_state.current_path,
    # Define a função de callback para alteração do diretório, que atualiza o controller e força um rerender.
    set_current_directory_path_func=lambda path: (system_data.set_current_directory_path(path), system_data.update())
)

# Lógica para processar a entrada do usuário para o número de processos a visualizar.
try:
    new_num_processes_limit = int(num_processes_input_str_from_view)
    if new_num_processes_limit < 1: # Impede valores menores que 1.
        if new_num_processes_limit != st.session_state.num_processes_to_show:
             st.sidebar.warning(f"O número de processos deve ser pelo menos 1. Mantendo {st.session_state.num_processes_to_show}.")
        new_num_processes_limit = st.session_state.num_processes_to_show
except ValueError: # Trata casos em que a entrada não é um número.
    new_num_processes_limit = st.session_state.num_processes_to_show
    if num_processes_input_str_from_view != str(st.session_state.num_processes_to_show):
        st.sidebar.warning(f"Entrada '{num_processes_input_str_from_view}' inválida para número de processos. Mantendo {st.session_state.num_processes_to_show}.")

# Se o limite de processos foi alterado, atualiza o estado e reinicia a thread de coleta de dados.
if new_num_processes_limit != st.session_state.num_processes_to_show:
    st.session_state.num_processes_to_show = new_num_processes_limit
    start_background_thread(interval=2, limit=st.session_state.num_processes_to_show)
    st.rerun() # Força a reexecução do script para aplicar a mudança.
else:
    # Garante que a thread de coleta de dados esteja sempre rodando com o limite atual.
    start_background_thread(interval=2, limit=st.session_state.num_processes_to_show)