import streamlit as st  # Importa a biblioteca Streamlit para construir a interface.
import pandas as pd     # Importa a biblioteca Pandas para manipulação de dados, especialmente para criar DataFrames.
from datetime import datetime # Importa datetime para obter e formatar o timestamp da última atualização.

def format_bytes_rate(bytes_val):
    """
    Formata um valor numérico de bytes por segundo (B/s) em uma string legível,
    convertendo para KB/s, MB/s ou GB/s conforme apropriado, com duas casas decimais
    para KB/s, MB/s, GB/s e uma para B/s.

    Args:
        bytes_val (int or float): O valor da taxa em bytes por segundo.

    Returns:
        str: Uma string formatada representando a taxa (ex: "10.52 MB/s", "500.0 B/s").
             Retorna "0.0 B/s" se a entrada for inválida (não numérica) ou negativa.
    """
    if not isinstance(bytes_val, (int, float)) or bytes_val < 0: # Validação da entrada.
        return "0.0 B/s"
    if bytes_val >= 1024 * 1024 * 1024:  # Se maior ou igual a 1 GB/s
        return f"{bytes_val / (1024**3):.2f} GB/s" # Formata para GB/s com 2 casas decimais.
    elif bytes_val >= 1024 * 1024:  # Se maior ou igual a 1 MB/s
        return f"{bytes_val / (1024**2):.2f} MB/s" # Formata para MB/s com 2 casas decimais.
    elif bytes_val >= 1024:  # Se maior ou igual a 1 KB/s
        return f"{bytes_val / 1024:.2f} KB/s" # Formata para KB/s com 2 casas decimais.
    else:  # Caso contrário, é B/s
        return f"{bytes_val:.1f} B/s" # Formata para B/s com 1 casa decimal.

def format_memory_kb_to_mb_gb(kb_value):
    """
    Converte um valor de memória em Kilobytes (KB) para uma string formatada
    em KB, Megabytes (MB) ou Gigabytes (GB), de forma legível, usando a unidade
    mais apropriada. Para KB, mostra como inteiro; para MB/GB, com duas casas decimais.

    Args:
        kb_value (int or float): O valor da memória em KB.

    Returns:
        str: Uma string formatada representando a memória (ex: "100 KB", "1.52 GB", "0 KB").
             Retorna "0 KB" se a entrada for inválida, negativa ou zero.
    """
    if not isinstance(kb_value, (int, float)) or kb_value < 0: # Validação da entrada.
        return "0 KB" 
    if kb_value == 0:
        return "0 KB" 

    if kb_value >= 1024 * 1024:  # Se maior ou igual a 1 GB (1024*1024 KB)
        return f"{kb_value / (1024*1024):.2f} GB" # Formata para GB com 2 casas decimais.
    elif kb_value >= 1024:  # Se maior ou igual a 1 MB (1024 KB)
        return f"{kb_value / 1024:.2f} MB" # Formata para MB com 2 casas decimais.
    else:  # Caso contrário, é KB
        return f"{int(kb_value)} KB" # Formata para KB como inteiro (remove decimais).



def display_main_layout(global_info_data, processes_data, get_process_details_func, current_num_processes_value):
    """
    Define e exibe o layout principal da interface do dashboard.
    Esta função organiza como as diferentes seções (visão geral, tabela de processos, detalhes de processo)
    são apresentadas na página do Streamlit.

    Inclui:
    - Título do dashboard e carimbo de data/hora da última atualização da interface.
    - Seção de "Visão Geral do Sistema" (chamando `display_global_info`).
    - Campo de entrada (text_input) para o usuário definir o número de processos a serem visualizados na tabela.
    - Seção de "Processos" (chamando `display_processes_table` para mostrar a tabela).
    - Campo de entrada (text_input) para o usuário inserir um PID para visualização de detalhes específicos.
    - Seção de "Detalhes de um Processo Específico" (chamando `display_process_details` se um PID válido for fornecido).

    Args:
        global_info_data (dict): Dados globais do sistema (CPU, memória, etc.).
        processes_data (list): Lista de dicionários, cada um com dados de um processo.
        get_process_details_func (function): A função `model.get_process_details` que será chamada
                                             quando o usuário solicitar detalhes de um PID.
        current_num_processes_value (int): O número atual de processos configurado para exibição na tabela
                                           (usado como valor padrão no campo de entrada).

    Returns:
        str: O valor (string) inserido pelo usuário no campo de texto "Quantos processos visualizar?".
             Este valor é retornado para `app.py` para ser processado (convertido para int, validado,
             e usado para atualizar o limite de processos).
    """
    st.title("Dashboard de Monitoramento de Sistema")
    st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}") 

    st.subheader("Visão Geral do Sistema")
    display_global_info(global_info_data) # Chama a função para exibir as métricas globais.
    st.markdown("---")

    # Campo de texto para o usuário definir quantos processos listar na tabela.
    # `st.text_input` retorna o valor atual do campo como uma string.
    num_processes_input_val_str = st.text_input( 
        "Quantos processos visualizar?", 
        value=str(current_num_processes_value), # Valor padrão do campo (convertido para string).
    )

    st.subheader(f"Processos")
    display_processes_table(processes_data) # Chama a função para exibir a tabela de processos.
    st.markdown("---") 

    st.subheader("Detalhes de um Processo Específico")

    # Campo de texto para o usuário inserir um PID para ver detalhes.
    pid_input_str = st.text_input( 
        label="Digite o ID do processo para ver detalhes:",
        key="pid_details_text_input",
        placeholder="Ex: 1234"
    )

    if pid_input_str: # Se o usuário inseriu algo no campo de PID.
        try:
            selected_pid = int(pid_input_str) # Tenta converter a entrada para um inteiro.
            # Mostra um spinner ("Carregando...") enquanto busca os detalhes do processo.
            with st.spinner(f"Carregando detalhes para PID {selected_pid}..."):
                # Chama a função `get_process_details_func` (que é `model.get_process_details`)
                # para buscar os detalhes do PID selecionado.
                details = get_process_details_func(selected_pid)

            if details: # Se os detalhes foram encontrados (a função não retornou None).
                # Chama `display_process_details` para exibir as informações detalhadas.
                display_process_details(details, processes_data, selected_pid)
            else: # Se `details` for None (processo não encontrado ou erro ao buscar).
                st.warning(f"Processo com PID {selected_pid} não encontrado ou os dados não puderam ser acessados.")
        except ValueError: # Se a conversão de `pid_input_str` para `int` falhar (ex: usuário digitou texto).
            st.error("PID inválido. Por favor, insira apenas números (ex: 1234).")

    st.markdown("<br>" * 5, unsafe_allow_html=True)

    # Retorna o valor (string) do campo de entrada "Quantos processos visualizar?".
    # Este valor será usado em `app.py` para atualizar o limite de processos.
    return num_processes_input_val_str

def display_global_info(global_info):
    """
    Exibe as informações globais do sistema em métricas formatadas usando colunas do Streamlit.

    As informações incluem:
    - Uso de CPU (%) e CPU Ocioso (%)
    - Memória Usada (absoluto formatado em MB/GB e percentual) e Memória Livre (%)
    - Taxas de Leitura e Escrita de Disco (formatadas em KB/s, MB/s, etc.)
    - Total de Processos e Total de Threads no sistema.

    Args:
        global_info (dict): Um dicionário contendo os dados globais do sistema.
                           Espera-se chaves como "CPU (%)", "Memória Usada (KB)",
                           "Leitura Disco (B/s)", "Total de Processos", etc.
                           Valores ausentes são tratados com `.get(chave, valor_padrao)`.
    """
    
    col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns(9) 

    col1.metric("CPU (%)", global_info.get("CPU (%)", 0.0))
    
    col2.metric("CPU Ocioso (%)", global_info.get("CPU ocioso (%)", 0.0)) 
    
    # Obtém o valor em KB do dicionário.
    mem_used_kb_from_global = global_info.get("Memória Usada (KB)", 0) 
    
    # Formata o valor de KB para MB/GB usando a função auxiliar e exibe.
    col3.metric("Memória Usada", format_memory_kb_to_mb_gb(mem_used_kb_from_global)) 

    col4.metric("Memória Usada (%)", global_info.get("Memória (%)", 0.0)) 

    col5.metric("Memória Livre (%)", global_info.get("Memória Livre (%)", 0.0)) 

    # Formata a taxa de bytes/s usando a função auxiliar.
    col6.metric("Leitura Disco", format_bytes_rate(global_info.get("Leitura Disco (B/s)", 0.0))) 
    
    col7.metric("Escrita Disco", format_bytes_rate(global_info.get("Escrita Disco (B/s)", 0.0))) 

    col8.metric("Total de Processos", global_info.get("Total de Processos", 0)) 
    
    col9.metric("Total de Threads", global_info.get("Total de Threads", 0)) 

def display_processes_table(processes):
    """
    Exibe uma tabela formatada com a lista de processos e suas informações.
    Utiliza o Pandas para criar um DataFrame a partir da lista de processos,
    renomeia e reordena colunas para melhor apresentação.
    A tabela é renderizada como Markdown.

    Args:
        processes (list): Uma lista de dicionários, onde cada dicionário representa
                          um processo e suas métricas (PID, nome, %CPU, memória, etc.).
    """
    if not processes:
        st.info("Nenhum processo para exibir ou aguardando atualização.")
        return
    
    # Cria um DataFrame do Pandas a partir da lista de dicionários de processos.
    # Cada chave no dicionário se torna uma coluna no DataFrame.
    df_proc = pd.DataFrame(processes)

    # Dicionário para renomear as colunas do DataFrame
    rename_dict = { 
        'pid': 'ID', 'name': 'Nome', 'username': 'Usuário', 
        'threads': 'Nº Threads', 
        'cpu_percent': '% CPU', 'cpu_time': 'Tempo CPU (s)', 
        'memory_percent': '% Memória', 'memory_mb': 'Memória (MB)', 
        'io_read_bps': 'Leitura Disco (B/s)', 
        'io_write_bps': 'Escrita Disco (B/s)' 
    }
    # Aplica a renomeação das colunas.
    df_proc = df_proc.rename(columns=lambda c: rename_dict.get(c, c))

    # Define a ordem
    preferred_order = [ 
        'ID', 'Nome', 'Usuário', 
        '% CPU', 'Tempo CPU (s)', 
        'Nº Threads', 
        'Memória (MB)', '% Memória', 
        'Leitura Disco (B/s)', 'Escrita Disco (B/s)' 
    ]

    # Filtra as colunas para exibir apenas aquelas que existem no DataFrame E estão na lista `preferred_order`.
    cols_to_display = [col for col in preferred_order if col in df_proc.columns] 

    if not cols_to_display: # Se, após o filtro, não houver colunas para exibir.
        st.write("Dados de processos incompletos ou colunas não encontradas.")
        return

    # Cria uma cópia do DataFrame contendo apenas as colunas a serem exibidas e na ordem correta.
    df_proc_display = df_proc[cols_to_display].copy() 

    # Define formatadores para colunas específicas, melhorando a visualização dos dados numéricos.
    # Usa funções lambda para aplicar a formatação.
    formatters = { 
        '% CPU': lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else x, # Formata %CPU com 1 casa decimal.
        'Memória (MB)': lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x, # Formata Memória (MB) com 2 casas decimais.
        '% Memória': lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else x, # Formata % Memória com 1 casa decimal.
        'Tempo CPU (s)': lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x, # Formata Tempo CPU com 2 casas decimais.
        'Leitura Disco (B/s)': lambda x: format_bytes_rate(x) if isinstance(x, (int, float)) else x, # Usa `format_bytes_rate` para formatar.
        'Escrita Disco (B/s)': lambda x: format_bytes_rate(x) if isinstance(x, (int, float)) else x, # Usa `format_bytes_rate` para formatar.
    }
    
    # Aplica os formatadores a cada coluna correspondente no DataFrame.
    for col_name, func in formatters.items(): # Itera sobre o dicionário de formatadores.
        if col_name in df_proc_display.columns: # Verifica se a coluna existe no DataFrame a ser exibido.
            df_proc_display[col_name] = df_proc_display[col_name].apply(func) # Aplica a função de formatação à coluna.

    #CSS customizado para a tabela Markdown gerada:
    st.markdown("""
        <style>
        div[data-testid="stMarkdownContainer"] > table { width: 100%; }
        div[data-testid="stMarkdownContainer"] > table > thead > tr > th,
        div[data-testid="stMarkdownContainer"] > table > tbody > tr > td {
            text-align: center !important;
            padding: 8px !important;
        }
        </style>
    """, unsafe_allow_html=True) # `unsafe_allow_html=True` é necessário para injetar CSS.
    
    # Renderiza o DataFrame formatado como uma tabela Markdown.
    # `index=False` remove o índice do DataFrame da tabela exibida.
    st.markdown(df_proc_display.to_markdown(index=False), unsafe_allow_html=True) 

def format_memory_from_status(value_str):
    """
    Formata uma string de memória (geralmente de /proc/[pid]/status, no formato "1234 kB")
    para um formato mais legível (KB, MB, GB) usando a função `format_memory_kb_to_mb_gb`.
    
    Args:
        value_str (str): A string contendo o valor da memória e a unidade "kB"
                         (ex: "1234 kB", " 5678 kB ").

    Returns:
        str: A string de memória formatada (ex: "1.2 MB", "5 GB").
             Retorna a string original se a formatação falhar ou se a string
             não estiver no formato esperado (não contiver "kb").
    """
    # Verifica se `value_str` é uma string e se contém "kb".
    if isinstance(value_str, str) and "kb" in value_str.lower(): # Checa se é string e contém "kb"
        try:
            # Converte a string para minúsculas, remove "kb", remove espaços em branco
            # no início/fim, e então converte para inteiro.
            kb_value = int(value_str.lower().replace("kb", "").strip()) # Converte para inteiro após remover "kb" e espaços
            # Reutiliza a função de formatação principal `format_memory_kb_to_mb_gb`
            # para converter o valor KB para uma string formatada em KB/MB/GB.
            return format_memory_kb_to_mb_gb(kb_value)
        except ValueError: # Se a conversão para `int` falhar.
            return value_str # Retorna a string original em caso de erro na conversão.
    return value_str # Retorna a string original se não for uma string ou não contiver "kb".

def display_process_details(details, processes_data, current_pid):
    """
    Exibe informações detalhadas de um processo específico, incluindo dados gerais e de memória.
    Os detalhes são obtidos do `model.py` (passados via `details`).
    A %CPU atual do processo é buscada na lista `processes_data` (que contém dados mais recentes de todos os processos).

    As informações gerais incluem: Nome, Usuário, Estado, %CPU, Nº Threads, Hora de Início, Tempo de CPU, Prioridade, Nice.
    As informações de memória incluem: Memória Alocada (Residente, Virtual, Compartilhada, Gravável)
    e Páginas de Memória (Total Residente/Virtual, Código, Dados/Heap, Stack).

    Args:
        details (dict): Dicionário com os detalhes do processo obtidos de `model.get_process_details()`.
        processes_data (list): Lista de todos os processos (usada para obter a %CPU mais atualizada,
                               pois `details` pode ter uma %CPU ligeiramente defasada se não for recalculada lá).
        current_pid (int): O PID do processo cujos detalhes estão sendo exibidos.
    """
    if not details:
        st.warning("⚠️ Não foi possível acessar os detalhes deste processo.")
        return

    st.subheader(f"Detalhes do Processo PID: {details.get('PID', 'N/A')}")

    # Busca a %CPU atual do processo na lista `processes_data` (que é atualizada mais frequentemente
    # para a tabela principal). O `details` do model pode não ter a %CPU instantânea.
    cpu_percent_str = "N/A"
    if processes_data:
        for proc_info in processes_data: # Itera sobre os processos.
            if proc_info.get('pid') == current_pid: # Encontra o processo pelo PID.
                cpu_percent_val = proc_info.get('cpu_percent') # Pega o valor da %CPU.
                if isinstance(cpu_percent_val, (float, int)): # Se for um número.
                    cpu_percent_str = f"{cpu_percent_val:.1f}%" # Formata com 1 casa decimal.
                break # Sai do loop após encontrar o processo.

    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.markdown(f"**Nome:** {details.get('Nome', 'N/A')}")
        st.markdown(f"**Usuário:** {details.get('Usuário', 'N/A')}")
        st.markdown(f"**Estado:** {details.get('Estado', 'N/A')}")
        st.markdown(f"**CPU:** {cpu_percent_str}") 
        st.markdown(f"**Número de Threads:** {details.get('Número de Threads', 'N/A')}")

    with col_info2:
        st.markdown(f"**Iniciado:** {details.get('Iniciado', 'N/A')}")
        st.markdown(f"**Tempo da CPU:** {details.get('Tempo da CPU (s)', 'N/A')} s") 
        st.markdown(f"**Prioridade:** {details.get('Prioridade', 'N/A')}") 
        st.markdown(f"**Nice:** {details.get('Nice', 'N/A')}")

    st.markdown("---")
    st.markdown("##### Informações de Memória do Processo")

    mem_col1, mem_col2 = st.columns(2) 

    with mem_col1:
        st.markdown("**Memória Alocada:**")
        # Usa `format_memory_from_status` para formatar os valores que vêm como "XXXX kB" do model.
        # `&nbsp;&nbsp;&nbsp;&nbsp;` é usado para indentação.
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Residente (VmRSS): {format_memory_from_status(details.get('Memória Residente (VmRSS)', 'N/A'))}") 
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Virtual (VmSize): {format_memory_from_status(details.get('Memória Virtual (VmSize)', 'N/A'))}") 
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Compartilhada Residente (RssShmem): {format_memory_from_status(details.get('Memória Compartilhada (RssShmem)', 'N/A'))}") 
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Gravável (VmData): {format_memory_from_status(details.get('Memória Gravável (VmData)', 'N/A'))}")

    with mem_col2:
        st.markdown("**Páginas de Memória:**")
        
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Totais (Residente): {details.get('Páginas Totais Residente', 'N/A')}") 
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Totais (Virtual): {details.get('Páginas Totais Virtual', 'N/A')}") 
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Código (VmExe): {details.get('Páginas de Código (VmExe)', 'N/A')}") 
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Dados/Heap (VmData): {details.get('Páginas de Dados/Heap (VmData)', 'N/A')}") 
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Stack (VmStk): {details.get('Páginas de Stack (VmStk)', 'N/A')}") 

    st.markdown("---")
