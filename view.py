# view.py

import streamlit as st
import pandas as pd
from datetime import datetime

def format_bytes_rate(bytes_val):
    """
    Formata um valor numérico de bytes por segundo em uma string legível por humanos,
    convertendo para KB/s, MB/s ou GB/s conforme apropriado.

    Args:
        bytes_val (int or float): O valor em bytes por segundo.

    Returns:
        str: Uma string formatada representando a taxa (ex: "10.5 MB/s", "500.0 B/s").
             Retorna "0.0 B/s" se a entrada for inválida ou negativa.
    """
    if not isinstance(bytes_val, (int, float)) or bytes_val < 0:
        return "0.0 B/s"
    if bytes_val >= 1024 * 1024 * 1024:  # GB/s
        return f"{bytes_val / (1024**3):.2f} GB/s"
    elif bytes_val >= 1024 * 1024:  # MB/s
        return f"{bytes_val / (1024**2):.2f} MB/s"
    elif bytes_val >= 1024:  # KB/s
        return f"{bytes_val / 1024:.2f} KB/s"
    else:  # B/s
        return f"{bytes_val:.1f} B/s"

def format_memory_kb_to_mb_gb(kb_value):
    """
    Converte um valor de memória em Kilobytes (KB) para uma string formatada
    em KB, Megabytes (MB) ou Gigabytes (GB), de forma legível.

    Args:
        kb_value (int or float): O valor da memória em KB.

    Returns:
        str: Uma string formatada representando a memória (ex: "100 KB", "1.5 GB").
             Retorna "0 KB" se a entrada for inválida, negativa ou zero.
    """
    if not isinstance(kb_value, (int, float)) or kb_value < 0:
        return "0 KB"
    if kb_value == 0:
        return "0 KB"

    if kb_value >= 1024 * 1024:  # GB
        return f"{kb_value / (1024*1024):.2f} GB"
    elif kb_value >= 1024:  # MB
        return f"{kb_value / 1024:.2f} MB"
    else:  # KB
        return f"{int(kb_value)} KB"

def display_global_info(global_info):
    """
    Exibe as informações globais do sistema em métricas formatadas usando colunas do Streamlit.

    As informações incluem:
    - Uso de CPU (%) e CPU Ocioso (%)
    - Memória Usada (absoluto e percentual) e Memória Livre (%)
    - Taxas de Leitura e Escrita de Disco
    - Total de Processos e Total de Threads

    Args:
        global_info (dict): Um dicionário contendo os dados globais do sistema.
                           Espera-se chaves como "CPU (%)", "Memória Usada (KB)", etc.
    """
    # Define 9 colunas para as métricas
    col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns(9)

    # Métricas de CPU
    col1.metric("CPU (%)", global_info.get("CPU (%)", 0.0)) #
    col2.metric("CPU Ocioso (%)", global_info.get("CPU ocioso (%)", 0.0)) #

    # Coluna 3: Memória Usada em valor absoluto (MB/GB)
    mem_used_kb_from_global = global_info.get("Memória Usada (KB)", 0) #
    col3.metric("Memória Usada", format_memory_kb_to_mb_gb(mem_used_kb_from_global)) #

    # Coluna 4: Memória Usada em %
    col4.metric("Memória Usada (%)", global_info.get("Memória (%)", 0.0)) #

    # Coluna 5: Memória Livre em %
    col5.metric("Memória Livre (%)", global_info.get("Memória Livre (%)", 0.0)) #

    # Métricas de Disco
    col6.metric("Leitura Disco", format_bytes_rate(global_info.get("Leitura Disco (B/s)", 0.0))) #
    col7.metric("Escrita Disco", format_bytes_rate(global_info.get("Escrita Disco (B/s)", 0.0))) #

    # Contadores Globais
    col8.metric("Total de Processos", global_info.get("Total de Processos", 0)) #
    col9.metric("Total de Threads", global_info.get("Total de Threads", 0)) #

def display_processes_table(processes):
    """
    Exibe uma tabela formatada com a lista de processos e suas informações.

    A tabela inclui colunas como ID, Nome, Usuário, % CPU, Tempo de CPU,
    Nº Threads, Memória (MB e %), Leitura e Escrita de Disco (B/s).
    Os dados são formatados para melhor legibilidade.

    Args:
        processes (list): Uma lista de dicionários, onde cada dicionário representa
                          um processo e suas métricas.
    """
    if not processes: #
        st.info("Nenhum processo para exibir ou aguardando atualização.") #
        return
    df_proc = pd.DataFrame(processes) #

    # Dicionário para renomear as colunas do DataFrame para exibição.
    rename_dict = { #
        'pid': 'ID', 'name': 'Nome', 'username': 'Usuário', #
        'threads': 'Nº Threads', #
        'cpu_percent': '% CPU', 'cpu_time': 'Tempo CPU (s)', #
        'memory_percent': '% Memória', 'memory_mb': 'Memória (MB)', #
        'io_read_bps': 'Leitura Disco (B/s)', #
        'io_write_bps': 'Escrita Disco (B/s)' #
    }
    df_proc = df_proc.rename(columns=lambda c: rename_dict.get(c, c)) #

    # Define a ordem preferencial das colunas na tabela.
    preferred_order = [ #
        'ID', 'Nome', 'Usuário', #
        '% CPU', 'Tempo CPU (s)', #
        'Nº Threads', #
        'Memória (MB)', '% Memória', #
        'Leitura Disco (B/s)', 'Escrita Disco (B/s)' #
    ]

    # Filtra as colunas para exibir apenas aquelas que existem no DataFrame.
    cols_to_display = [col for col in preferred_order if col in df_proc.columns] #

    if not cols_to_display: #
        st.write("Dados de processos incompletos ou colunas não encontradas.") #
        return

    df_proc_display = df_proc[cols_to_display].copy() #

    # Define formatadores para colunas específicas, melhorando a visualização dos dados.
    formatters = { #
        '% CPU': lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else x, #
        'Memória (MB)': lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x, #
        '% Memória': lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else x, #
        'Tempo CPU (s)': lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x, #
        'Leitura Disco (B/s)': lambda x: format_bytes_rate(x) if isinstance(x, (int, float)) else x, #
        'Escrita Disco (B/s)': lambda x: format_bytes_rate(x) if isinstance(x, (int, float)) else x, #
    }
    for col_name, func in formatters.items(): #
        if col_name in df_proc_display.columns: #
            df_proc_display[col_name] = df_proc_display[col_name].apply(func) #

    # Aplica CSS customizado para a tabela (largura, alinhamento do texto, padding).
    st.markdown("""
        <style>
        div[data-testid="stMarkdownContainer"] > table { width: 100%; }
        div[data-testid="stMarkdownContainer"] > table > thead > tr > th,
        div[data-testid="stMarkdownContainer"] > table > tbody > tr > td {
            text-align: center !important;
            padding: 8px !important;
        }
        </style>
    """, unsafe_allow_html=True) #
    # Renderiza o DataFrame como uma tabela Markdown.
    st.markdown(df_proc_display.to_markdown(index=False), unsafe_allow_html=True) #

def format_memory_from_status(value_str):
    """
    Formata uma string de memória (geralmente de /proc/[pid]/status, ex: "1234 kB")
    para um formato mais legível (KB, MB, GB) usando a função format_memory_kb_to_mb_gb.

    Args:
        value_str (str): A string contendo o valor da memória e a unidade "kB".

    Returns:
        str: A string de memória formatada ou a string original se a formatação falhar.
    """
    if isinstance(value_str, str) and "kb" in value_str.lower(): # Checa se é string e contém "kb" (case-insensitive)
        try:
            kb_value = int(value_str.lower().replace("kb", "").strip()) # Converte para inteiro após remover "kb" e espaços
            return format_memory_kb_to_mb_gb(kb_value) # Reutiliza a função de formatação principal
        except ValueError: #
            return value_str # Retorna original em caso de erro na conversão
    return value_str # Retorna original se não for string ou não contiver "kb"

def display_process_details(details, processes_data, current_pid):
    """
    Exibe informações detalhadas de um processo específico, incluindo dados gerais e de memória.

    As informações gerais incluem Nome, Usuário, Estado, % CPU, Threads, Início, Tempo de CPU, etc.
    As informações de memória incluem Memória Alocada (Residente, Virtual, Compartilhada, Gravável)
    e Páginas de Memória (Total Residente/Virtual, Código, Dados/Heap, Stack).

    Args:
        details (dict): Dicionário com os detalhes do processo obtidos do model.py.
        processes_data (list): Lista de todos os processos (usada para obter a %CPU atual).
        current_pid (int): O PID do processo cujos detalhes estão sendo exibidos.
    """
    if not details: #
        st.warning("⚠️ Não foi possível acessar os detalhes deste processo.") #
        return

    st.subheader(f"Detalhes do Processo PID: {details.get('PID', 'N/A')}") #

    # Busca a %CPU atual do processo na lista de processos globais.
    cpu_percent_str = "N/A" #
    if processes_data: #
        for proc_info in processes_data: #
            if proc_info.get('pid') == current_pid: #
                cpu_percent_val = proc_info.get('cpu_percent') #
                if isinstance(cpu_percent_val, (float, int)): #
                    cpu_percent_str = f"{cpu_percent_val:.1f}%" #
                break #

    # Exibe informações gerais do processo em duas colunas.
    col_info1, col_info2 = st.columns(2) #
    with col_info1: #
        st.markdown(f"**Nome:** {details.get('Nome', 'N/A')}") #
        st.markdown(f"**Usuário:** {details.get('Usuário', 'N/A')}") #
        st.markdown(f"**Estado:** {details.get('Estado', 'N/A')}") #
        st.markdown(f"**CPU:** {cpu_percent_str}") #
        st.markdown(f"**Número de Threads:** {details.get('Número de Threads', 'N/A')}") #

    with col_info2: #
        st.markdown(f"**Iniciado:** {details.get('Iniciado', 'N/A')}") #
        st.markdown(f"**Tempo da CPU:** {details.get('Tempo da CPU (s)', 'N/A')} s") #
        st.markdown(f"**Prioridade:** {details.get('Prioridade', 'N/A')}") #
        st.markdown(f"**Nice:** {details.get('Nice', 'N/A')}") #

    st.markdown("---") #
    st.markdown("##### Informações de Memória do Processo") #

    # Exibe informações de memória do processo em duas colunas.
    mem_col1, mem_col2 = st.columns(2) #

    with mem_col1: #
        st.markdown("**Memória Alocada:**") #
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Residente (VmRSS): {format_memory_from_status(details.get('Memória Residente (VmRSS)', 'N/A'))}") #
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Virtual (VmSize): {format_memory_from_status(details.get('Memória Virtual (VmSize)', 'N/A'))}") #
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Compartilhada Residente (RssShmem): {format_memory_from_status(details.get('Memória Compartilhada (RssShmem)', 'N/A'))}") #
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Gravável (VmData): {format_memory_from_status(details.get('Memória Gravável (VmData)', 'N/A'))}") #

    with mem_col2: #
        st.markdown("**Páginas de Memória:**") #
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Totais (Residente): {details.get('Páginas Totais Residente', 'N/A')}") #
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Totais (Virtual): {details.get('Páginas Totais Virtual', 'N/A')}") #
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Código (VmExe): {details.get('Páginas de Código (VmExe)', 'N/A')}") #
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Dados/Heap (VmData): {details.get('Páginas de Dados/Heap (VmData)', 'N/A')}") #
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Stack (VmStk): {details.get('Páginas de Stack (VmStk)', 'N/A')}") #

    st.markdown("---") #


def display_main_layout(global_info_data, processes_data, get_process_details_func, current_num_processes_value):
    """
    Define e exibe o layout principal da interface do dashboard.

    Inclui:
    - Título e carimbo de data/hora da última atualização.
    - Seção de "Visão Geral do Sistema" (chamando display_global_info).
    - Campo de entrada para o número de processos a serem visualizados.
    - Seção de "Processos" (chamando display_processes_table).
    - Campo de entrada para o PID para visualização de detalhes específicos.
    - Seção de "Detalhes de um Processo Específico" (chamando display_process_details se um PID for fornecido).

    Args:
        global_info_data (dict): Dados globais do sistema.
        processes_data (list): Lista de dados dos processos.
        get_process_details_func (function): Função (do model) para buscar detalhes de um processo.
        current_num_processes_value (int): O número atual de processos configurado para exibição.

    Returns:
        str: O valor do campo de entrada para o número de processos a visualizar,
             para ser processado pelo app.py.
    """
    st.title("Dashboard de Monitoramento de Sistema") #
    st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}") #

    st.subheader("Visão Geral do Sistema") #
    display_global_info(global_info_data) # Chama a função para exibir métricas globais
    st.markdown("---") #

    # Campo para o usuário definir quantos processos listar.
    num_processes_input_val_str = st.text_input( #
        "Quantos processos visualizar?", #
        value=str(current_num_processes_value), #
        help="Insira o número de processos para listar (ex: 10, 500). Um valor alto pode impactar o desempenho." #
    )

    st.subheader(f"Processos") #
    display_processes_table(processes_data) # Chama a função para exibir a tabela de processos
    st.markdown("---") #

    st.subheader("Detalhes de um Processo Específico") #

    # Campo para o usuário inserir um PID para ver detalhes.
    pid_input_str = st.text_input( #
        label="Digite o ID do processo para ver detalhes:", #
        key="pid_details_text_input", #
        placeholder="Ex: 1234" #
    )

    if pid_input_str: # Se um PID foi inserido
        try:
            selected_pid = int(pid_input_str) # Tenta converter para inteiro
            with st.spinner(f"Carregando detalhes para PID {selected_pid}..."): # Mostra um spinner durante o carregamento
                details = get_process_details_func(selected_pid) # Busca os detalhes do processo

            if details: # Se os detalhes foram encontrados
                display_process_details(details, processes_data, selected_pid) # Exibe os detalhes
            else: # Se não encontrou o processo
                st.warning(f"Processo com PID {selected_pid} não encontrado ou os dados não puderam ser acessados.") #
        except ValueError: # Se o PID inserido não for um número
            st.error("PID inválido. Por favor, insira apenas números (ex: 1234).") #

    st.markdown("<br>" * 5, unsafe_allow_html=True) # Adiciona espaço no final da página

    return num_processes_input_val_str # Retorna o valor do input do número de processos