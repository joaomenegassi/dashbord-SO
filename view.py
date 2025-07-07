import streamlit as st
import pandas as pd
from datetime import datetime
import os
import stat
from pathlib import Path

def format_bytes_rate(bytes_val):
    """
    Formata um valor numérico de bytes por segundo (B/s) em uma string legível.
    """
    if not isinstance(bytes_val, (int, float)) or bytes_val < 0:
        return "0.0 B/s"
    if bytes_val >= 1024 * 1024 * 1024:
        return f"{bytes_val / (1024**3):.2f} GB/s"
    elif bytes_val >= 1024 * 1024:
        return f"{bytes_val / (1024**2):.2f} MB/s"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.2f} KB/s"
    else:
        return f"{bytes_val:.1f} B/s"

def format_memory_kb_to_mb_gb(kb_value):
    """
    Converte um valor de memória em Kilobytes (KB) para uma string formatada
    em KB, Megabytes (MB) ou Gigabytes (GB).
    """
    if not isinstance(kb_value, (int, float)) or kb_value < 0:
        return "0 KB"
    if kb_value == 0:
        return "0 KB"

    if kb_value >= 1024 * 1024:
        return f"{kb_value / (1024*1024):.2f} GB"
    elif kb_value >= 1024:
        return f"{kb_value / 1024:.2f} MB"
    else:
        return f"{int(kb_value)} KB"

def format_file_size(size_bytes):
    """
    Formata um tamanho de arquivo em bytes para uma string legível (B, KB, MB, GB).
    """
    if not isinstance(size_bytes, (int, float)) or size_bytes < 0:
        return "N/A"
    if size_bytes >= 1024**3: # Gigabytes
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024**2: # Megabytes
        return f"{size_bytes / (1024**2):.2f} MB"
    elif size_bytes >= 1024: # Kilobytes
        return f"{size_bytes / 1024:.2f} KB"
    else: # Bytes
        return f"{size_bytes} B"

def display_main_layout(global_info_data, processes_data, get_process_details_func, current_num_processes_value, filesystem_data, directory_contents_data, current_path, set_current_directory_path_func):
    """
    Define e exibe o layout principal da interface do dashboard.
    """
    st.title("Dashboard de Monitoramento de Sistema")
    st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    # Adicionando a nova aba para detalhes de processos e recursos abertos
    tab_geral, tab_filesystem = st.tabs(["Geral", "Sistema de Arquivos"])

    with tab_geral:
        st.subheader("Visão Geral do Sistema")
        display_global_info(global_info_data)
        st.markdown("---")

        num_processes_input_val_str = st.text_input(
            "Quantos processos visualizar?",
            value=str(current_num_processes_value),
        )

        st.subheader(f"Processos")
        display_processes_table(processes_data)
        st.markdown("---")

        st.subheader("Detalhes de um Processo Específico")

        pid_input_str = st.text_input(
            label="Digite o ID do processo para ver detalhes:",
            key="pid_details_text_input",
            placeholder="Ex: 1234"
        )

        if pid_input_str:
            try:
                selected_pid = int(pid_input_str)
                with st.spinner(f"Carregando detalhes para PID {selected_pid}..."):
                    details = get_process_details_func(selected_pid)

                if details:
                    # Agora, display_process_details terá suas próprias abas internas
                    display_process_details(details, processes_data, selected_pid)
                else:
                    st.warning(f"Processo com PID {selected_pid} não encontrado ou os dados não puderam ser acessados.")
            except ValueError:
                st.error("PID inválido. Por favor, insira apenas números (ex: 1234).")

        st.markdown("<br>" * 5, unsafe_allow_html=True)

    with tab_filesystem:
        st.subheader("Visão Geral do Sistema de Arquivos")
        display_filesystem_info(filesystem_data)
        st.markdown("---")

        st.subheader(f"Navegação de Diretórios: `{current_path}`")

        parent_path = os.path.dirname(current_path)
        if current_path != "/":
            if st.button("Voltar", key="up_dir_button"):
                with st.spinner("Carregando diretório pai..."):
                    set_current_directory_path_func(parent_path)
                st.rerun()

        display_directory_navigation_buttons(directory_contents_data, set_current_directory_path_func)

        st.markdown("---")
        st.subheader("Conteúdo do Diretório Atual")
        display_files_table(directory_contents_data)


    return num_processes_input_val_str

def display_global_info(global_info):
    """
    Exibe as informações globais do sistema em métricas formatadas.
    """
    col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns(9)

    col1.metric("CPU (%)", global_info.get("CPU (%)", 0.0))
    col2.metric("CPU Ocioso (%)", global_info.get("CPU ocioso (%)", 0.0))
    mem_used_kb_from_global = global_info.get("Memória Usada (KB)", 0)
    col3.metric("Memória Usada", format_memory_kb_to_mb_gb(mem_used_kb_from_global))
    col4.metric("Memória Usada (%)", global_info.get("Memória (%)", 0.0))
    col5.metric("Memória Livre (%)", global_info.get("Memória Livre (%)", 0.0))
    col6.metric("Leitura Disco", format_bytes_rate(global_info.get("Leitura Disco (B/s)", 0.0)))
    col7.metric("Escrita Disco", format_bytes_rate(global_info.get("Escrita Disco (B/s)", 0.0)))
    col8.metric("Total de Processos", global_info.get("Total de Processos", 0))
    col9.metric("Total de Threads", global_info.get("Total de Threads", 0))

def display_processes_table(processes):
    """
    Exibe uma tabela formatada com a lista de processos e suas informações.
    """
    if not processes:
        st.info("Nenhum processo para exibir ou aguardando atualização.")
        return

    df_proc = pd.DataFrame(processes)

    rename_dict = {
        'pid': 'ID', 'name': 'Nome', 'username': 'Usuário',
        'threads': 'Nº Threads',
        'cpu_percent': '% CPU', 'cpu_time': 'Tempo CPU (s)',
        'memory_percent': '% Memória', 'memory_mb': 'Memória (MB)',
        'io_read_bps': 'Leitura Disco (B/s)',
        'io_write_bps': 'Escrita Disco (B/s)'
    }
    df_proc = df_proc.rename(columns=lambda c: rename_dict.get(c, c))

    preferred_order = [
        'ID', 'Nome', 'Usuário',
        '% CPU', 'Tempo CPU (s)',
        'Nº Threads',
        'Memória (MB)', '% Memória',
        'Leitura Disco (B/s)', 'Escrita Disco (B/s)'
    ]

    cols_to_display = [col for col in preferred_order if col in df_proc.columns]

    if not cols_to_display:
        st.write("Dados de processos incompletos ou colunas não encontradas.")
        return

    df_proc_display = df_proc[cols_to_display].copy()

    formatters = {
        '% CPU': lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else x,
        'Memória (MB)': lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x,
        '% Memória': lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else x,
        'Tempo CPU (s)': lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x,
        'Leitura Disco (B/s)': lambda x: format_bytes_rate(x) if isinstance(x, (int, float)) else x,
        'Escrita Disco (B/s)': lambda x: format_bytes_rate(x) if isinstance(x, (int, float)) else x,
    }

    for col_name, func in formatters.items():
        if col_name in df_proc_display.columns:
            df_proc_display[col_name] = df_proc_display[col_name].apply(func)

    st.markdown("""
        <style>
        div[data-testid="stMarkdownContainer"] > table { width: 100%; }
        div[data-testid="stMarkdownContainer"] > table > thead > tr > th,
        div[data-testid="stMarkdownContainer"] > table > tbody > tr > td {
            text-align: center !important;
            padding: 8px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown(df_proc_display.to_markdown(index=False), unsafe_allow_html=True)

def format_memory_from_status(value_str):
    """
    Formata uma string de memória (geralmente de /proc/[pid]/status, no formato "1234 kB")
    para um formato mais legível (KB, MB, GB).
    """
    if isinstance(value_str, str) and "kb" in value_str.lower():
        try:
            kb_value = int(value_str.lower().replace("kb", "").strip())
            return format_memory_kb_to_mb_gb(kb_value)
        except ValueError:
            return value_str
    return value_str

def display_process_details(details, processes_data, current_pid):
    """
    Exibe informações detalhadas de um processo específico em abas.
    """
    if not details:
        st.warning("⚠️ Não foi possível acessar os detalhes deste processo.")
        return

    st.subheader(f"Detalhes do Processo PID: {details.get('PID', 'N/A')}")

    # Criação das abas internas para os detalhes do processo
    tab_overview, tab_memory, tab_io = st.tabs(["Geral", "Memória", "I/O e Recursos"])

    with tab_overview:
        cpu_percent_str = "N/A"
        if processes_data:
            for proc_info in processes_data:
                if proc_info.get('pid') == current_pid:
                    cpu_percent_val = proc_info.get('cpu_percent')
                    if isinstance(cpu_percent_val, (float, int)):
                        cpu_percent_str = f"{cpu_percent_val:.1f}%"
                    break

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

    with tab_memory:
        st.markdown("##### Informações de Memória do Processo")

        mem_col1, mem_col2 = st.columns(2)

        with mem_col1:
            st.markdown("**Memória Alocada:**")
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

    with tab_io:
        st.markdown("##### Recursos Abertos e I/O do Processo")
        display_open_resources(details.get('Recursos Abertos', []))


def display_filesystem_info(filesystem_data):
    """
    Exibe as informações do sistema de arquivos.
    """
    if not filesystem_data or not filesystem_data.get('partitions'):
        st.info("Nenhum dado de sistema de arquivos disponível ainda ou aguardando atualização.")
        return

    st.markdown("---")

    partitions = filesystem_data.get('partitions', [])
    if partitions:
        st.subheader("Partições do Sistema")
        df_partitions = pd.DataFrame(partitions)

        df_partitions = df_partitions.rename(columns={
            'name': 'Nome da Partição',
            'mount_point': 'Ponto de Montagem',
            'fs_type': 'Tipo FS',
            'total_size_kb': 'Tamanho Total (KB)',
            'used_kb': 'Usado (KB)',
            'free_kb': 'Livre (KB)',
            'usage_percent': 'Uso (%)'
        })

        df_partitions['Tamanho Total (KB)'] = df_partitions['Tamanho Total (KB)'].apply(format_memory_kb_to_mb_gb)
        df_partitions['Usado (KB)'] = df_partitions['Usado (KB)'].apply(format_memory_kb_to_mb_gb)
        df_partitions['Livre (KB)'] = df_partitions['Livre (KB)'].apply(format_memory_kb_to_mb_gb)
        df_partitions['Uso (%)'] = df_partitions['Uso (%)'].apply(lambda x: f"{x:.2f}%")

        st.markdown("""
            <style>
            div[data-testid="stMarkdownContainer"] > table { width: 100%; }
            div[data-testid="stMarkdownContainer"] > table > thead > tr > th,
            div[data-testid="stMarkdownContainer"] > table > tbody > tr > td {
                text-align: center !important;
                padding: 8px !important;
            }
            </style>
        """, unsafe_allow_html=True)

        st.markdown(df_partitions.to_markdown(index=False), unsafe_allow_html=True)

    else:
        st.info("Nenhuma partição encontrada.")


def display_directory_navigation_buttons(contents, set_current_directory_path_func):
    """
    Exibe apenas os botões de diretório para navegação.
    """
    if not contents:
        return

    st.markdown("---")
    st.write("Clique em um diretório abaixo para navegar:")

    dir_buttons_cols = st.columns(5)

    i = 0
    for idx, item_dict in enumerate(contents):
        item_name = item_dict.get('name', 'N/A')
        item_type = item_dict.get('type', 'N/A')
        current_item_full_path = item_dict.get('full_path')

        # Apenas cria o botão se for um diretório e o caminho for acessível e existir
        if item_type == 'Diretório' and current_item_full_path and Path(current_item_full_path).is_dir():
            with dir_buttons_cols[i % 5]:
                if st.button(f" {item_name}", key=f"dir_button_{current_item_full_path}_{idx}"):
                    with st.spinner(f"Abrindo {item_name}..."):
                        set_current_directory_path_func(current_item_full_path)
                    st.rerun()
            i += 1

def display_files_table(contents):
    """
    Exibe uma tabela com os arquivos e seus atributos no diretório atual, incluindo o nome do proprietário.
    """
    if not contents:
        st.info("Nenhum arquivo para exibir no diretório atual.")
        return

    files_only = [item for item in contents if item.get('type') == 'Arquivo']

    if not files_only:
        st.info("Nenhum arquivo encontrado neste diretório.")
        return

    df_files = pd.DataFrame(files_only)

    df_files = df_files.rename(columns={
        'name': 'Nome do Arquivo',
        'type': 'Tipo',
        'size': 'Tamanho',
        'permissions_str': 'Permissões (String)',
        'last_modified': 'Última Modificação',
        'owner_username': 'Proprietário'  # Renomeia para 'Proprietário'
    })

    cols_to_display = [
        'Nome do Arquivo',
        'Tipo',
        'Tamanho',
        'Proprietário',  # Usa a nova coluna 'Proprietário'
        'Permissões (String)',
        'Última Modificação'
    ]

    df_files_display = df_files[[col for col in cols_to_display if col in df_files.columns]].copy()

    if 'Tamanho' in df_files_display.columns:
        df_files_display['Tamanho'] = df_files_display['Tamanho'].apply(format_file_size)

    st.markdown("""
        <style>
        div[data-testid="stMarkdownContainer"] > table { width: 100%; }
        div[data-testid="stMarkdownContainer"] > table > thead > tr > th,
        div[data-testid="stMarkdownContainer"] > table > tbody > tr > td {
            text-align: center !important;
            padding: 8px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown(df_files_display.to_markdown(index=False), unsafe_allow_html=True)

def display_open_resources(resources_data):
    """
    Exibe uma tabela com os recursos abertos (arquivos, sockets, pipes, etc.) por um processo.
    """
    if not resources_data:
        st.info("Nenhum recurso aberto encontrado ou permissão negada para este processo.")
        return

    df_resources = pd.DataFrame(resources_data)

    df_resources = df_resources.rename(columns={
        'fd': 'Descritor (FD)',
        'path': 'Caminho / Detalhe',
        'type': 'Tipo de Recurso'
    })

    cols_to_display = [
        'Descritor (FD)',
        'Tipo de Recurso',
        'Caminho / Detalhe'
    ]

    df_resources_display = df_resources[[col for col in cols_to_display if col in df_resources.columns]].copy()

    st.markdown("""
        <style>
        div[data-testid="stMarkdownContainer"] > table { width: 100%; }
        div[data-testid="stMarkdownContainer"] > table > thead > tr > th,
        div[data-testid="stMarkdownContainer"] > table > tbody > tr > td {
            text-align: center !important;
            padding: 8px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown(df_resources_display.to_markdown(index=False), unsafe_allow_html=True)