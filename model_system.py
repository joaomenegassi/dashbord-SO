import time # Para obter o tempo atual e calcular deltas.
from pathlib import Path # Para manipulação de caminhos de arquivos.
from datetime import datetime # Para formatar timestamps em datas legíveis.
import os # Para interagir com o sistema operacional (leitura de arquivos /proc).
import socket # Embora importado, não é usado diretamente para sockets de rede na coleta atual.
import re # Embora importado, não é usado diretamente para expressões regulares na coleta atual.

# Cache global para armazenar dados de chamadas anteriores.
# para calcular métricas baseadas em diferenças (deltas), como % de CPU e taxas de I/O.
cache = {
    # Armazena os últimos tempos de CPU do sistema (user, nice, system, idle, iowait, irq, softirq, steal).
    # Lidos de /proc/stat, são usados para calcular a % de CPU global.
    # Chave: 'idle' (int) - soma dos tempos ociosos, 'total' (int) - soma de todos os tempos.
    'prev_sys_cpu_times': {},
    # Armazena os últimos tempos de CPU (utime + stime em 'jiffies' ou 'clock ticks') para cada PID.
    # Usado para calcular a % de CPU de processos individuais. Chave: PID (str), Valor: total_ticks (int).
    'prev_times': {},
    # Timestamp (em segundos desde a Epoch) da última coleta de dados de processos.
    # Usado para calcular o 'elapsed_wall_time' (tempo real decorrido), necessário para normalizar
    # o uso de CPU do processo (delta de tempo de CPU do processo / delta de tempo real).
    'prev_timestamp': time.time(),
    # Cache para o total de memória RAM em KB. Evita releituras constantes do arquivo /proc/meminfo
    # se o valor não mudou (o que é geralmente o caso para MemTotal).
    'mem_total_kb': None,
    # Armazena as últimas estatísticas de I/O do disco (total_reads_bytes, total_writes_bytes agregados de todos os discos relevantes).
    # Usado para calcular as taxas de leitura/escrita globais do disco.
    'prev_disk_stats': {},
    # Timestamp da última coleta de dados de I/O de disco. Usado para calcular o delta de tempo para as taxas de I/O.
    'prev_disk_io_timestamp': time.time(),
    # Cache para estatísticas de I/O por processo (bytes lidos e escritos).
    # Lidos de /proc/[pid]/io. Chave: PID (str), Valor: {'read_bytes': int, 'write_bytes': int}.
    'prev_proc_io_stats': {},
}

# Constantes do sistema.
# CLK_TCK (Clock Ticks por Segundo): Define quantos 'jiffies' (unidade básica de tempo do kernel Linux)
# ocorrem em um segundo. O valor é tipicamente 100 em muitos sistemas Linux.
# Usado para converter tempos de CPU (reportados em jiffies em /proc/[pid]/stat) para segundos.
CLK_TCK = 100
# PAGE_SIZE: Tamanho de uma página de memória em bytes. Comum em arquiteturas x86/x86_64 é 4096 bytes (4KB).
# Usado para calcular o número de páginas de memória de um processo a partir de VmRSS, VmSize, etc. (que são em KB).
PAGE_SIZE = 4096
# SECTOR_SIZE: Tamanho de um setor de disco em bytes.
# /proc/diskstats reporta I/O em número de setores (geralmente 512 bytes por setor).
# Usado para converter o número de setores lidos/escritos em bytes.
SECTOR_SIZE = 512

# Cache para mapeamento de UID (User ID) para nome de usuário.
# Evita ler e parsear /etc/passwd repetidamente para o mesmo UID.
_user_cache = {}

def get_username_from_uid_local(uid_int):
    """
    Obtém o nome de usuário correspondente a um UID (User ID) lendo o arquivo /etc/passwd.
    Utiliza um cache interno (`_user_cache`) para otimizar chamadas repetidas para o mesmo UID,
    reduzindo operações de I/O de arquivo.

    Args:
        uid_int (int): O ID do usuário (numérico).

    Returns:
        str: O nome de usuário correspondente. Se não for encontrado ou em caso de erro
             (ex: /etc/passwd não encontrado), retorna o UID convertido para string.
    """
    # Retorna do cache se já presente.
    if uid_int in _user_cache:
        return _user_cache[uid_int]

    try:
        # Lê /etc/passwd para encontrar o nome de usuário pelo UID.
        with open('/etc/passwd', 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) > 2:
                    try:
                        if int(parts[2]) == uid_int:
                            username = parts[0]
                            _user_cache[uid_int] = username # Adiciona ao cache.
                            return username
                    except ValueError:
                        continue
    except FileNotFoundError:
        _user_cache[uid_int] = str(uid_int)
        return str(uid_int)

    _user_cache[uid_int] = str(uid_int)
    return str(uid_int)


def get_global_info():
    """
    Coleta informações globais do sistema, como uso de CPU, memória RAM,
    contagem total de processos e threads, e taxas de I/O de disco (leitura/escrita).
    Utiliza o `cache` global para calcular métricas baseadas em diferenças de tempo
    (deltas), como a porcentagem de uso da CPU e as taxas de I/O.

    Returns:
        dict: Um dicionário contendo as informações globais do sistema.
              Ex: {"CPU (%)": 7.5, "Memória Usada (KB)": 2048000, ...}
    """

    global cache
    current_timestamp = time.time()

    # --- Cálculo do Uso da CPU Global ---
    # Lê /proc/stat para obter os tempos de CPU acumulados.
    cpu_used_pct = 0.0
    cpu_ocioso_pct = 0.0
    try:
        with open('/proc/stat', 'r') as f:
            line = f.readline()
            fields = list(map(int, line.split()[1:]))

        current_ocioso = fields[3] + fields[4] # idle + iowait
        current_total = sum(fields)

        prev_ocioso = cache['prev_sys_cpu_times'].get('ocioso', 0)
        prev_total = cache['prev_sys_cpu_times'].get('total', 0)

        if prev_total > 0 and current_total > prev_total:
            total_diff = current_total - prev_total
            ocioso_diff = current_ocioso - prev_ocioso
            cpu_used_pct = (1.0 - (ocioso_diff / total_diff)) * 100 if total_diff > 0 else 0.0
            cpu_ocioso_pct = (ocioso_diff / total_diff) * 100 if total_diff > 0 else 0.0
        else:
            non_ocioso_time = fields[0] + fields[1] + fields[2] + fields[5] + fields[6] + fields[7]
            cpu_used_pct = (non_ocioso_time / current_total) * 100 if current_total > 0 else 0.0
            cpu_ocioso_pct = (fields[3] / current_total * 100) if current_total > 0 else 0.0

        cache['prev_sys_cpu_times']['ocioso'] = current_ocioso
        cache['prev_sys_cpu_times']['total'] = current_total

    except (FileNotFoundError, IndexError, ValueError, ZeroDivisionError) as e:
        print(f"Erro ao ler /proc/stat: {e}")

    # --- Cálculo do Uso da Memória RAM e SWAP ---
    # Lê /proc/meminfo para obter informações detalhadas sobre a memória.
    mem_used_pct = 0.0
    mem_free_pct = 0.0
    mem_used_absolute_kb = 0
    swap_total_kb = 0
    swap_free_kb = 0
    swap_used_kb = 0

    try:
        meminfo = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                chave, valor_str_com_unidade = line.split(':', 1)
                meminfo[chave.strip()] = int(valor_str_com_unidade.split()[0])

        total_mem_kb = meminfo.get('MemTotal', 1)
        avail_mem_kb = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))

        if cache['mem_total_kb'] is None or cache['mem_total_kb'] != total_mem_kb:
             cache['mem_total_kb'] = total_mem_kb

        if total_mem_kb > 0:
            mem_used_pct = (1.0 - (avail_mem_kb / total_mem_kb)) * 100
            mem_free_pct = (avail_mem_kb / total_mem_kb) * 100
            mem_used_absolute_kb = total_mem_kb - avail_mem_kb

        swap_total_kb = meminfo.get('SwapTotal', 0)
        swap_free_kb = meminfo.get('SwapFree', 0)
        swap_used_kb = swap_total_kb - swap_free_kb

    except (FileNotFoundError, ValueError, ZeroDivisionError) as e:
        print(f"Erro ao ler /proc/meminfo: {e}")
        mem_used_pct = 0.0
        mem_free_pct = 0.0
        mem_used_absolute_kb = 0
        swap_used_kb = 0

    # --- Contagem de Processos e Threads Totais no Sistema ---
    # Itera sobre os diretórios em /proc para contar PIDs e threads.
    proc_count = 0
    thread_count_global = 0
    for proc_dir_global in Path('/proc').iterdir():
        if proc_dir_global.is_dir() and proc_dir_global.name.isdigit():
            proc_count += 1
            try:
                with open(proc_dir_global / 'status', 'r') as sf_global:
                    for line_global in sf_global:
                        if line_global.startswith('Threads:'):
                            thread_count_global += int(line_global.split()[1])
                            break
            except (FileNotFoundError, PermissionError, ValueError):
                continue

    # --- Cálculo de I/O de Disco ---
    # Lê /proc/diskstats para obter estatísticas de I/O acumuladas dos discos.
    disk_read_bps = 0.0
    disk_write_bps = 0.0
    current_aggregated_reads_bytes = 0
    current_aggregated_writes_bytes = 0

    # Define prefixos de dispositivos de disco relevantes para filtragem.
    relevant_device_prefixes = ('sd', 'hd', 'vd', 'xvd')
    nvme_prefix = 'nvme'

    try:
        with open('/proc/diskstats', 'r') as f:
            for line in f:
                fields = line.split()
                if len(fields) < 10: continue
                device_name = fields[2]

                is_relevant = False
                for prefix in relevant_device_prefixes:
                    if device_name.startswith(prefix) and not any(char.isdigit() for char in device_name[len(prefix):]):
                        is_relevant = True
                        break
                if not is_relevant and device_name.startswith(nvme_prefix) and 'p' not in device_name[len(nvme_prefix):]:
                    is_relevant = True

                if device_name.startswith(('sr', 'loop', 'ram', 'dm-')):
                    is_relevant = False

                if is_relevant:
                    try:
                        sectors_read = int(fields[5])
                        sectors_written = int(fields[9])
                        current_aggregated_reads_bytes += sectors_read * SECTOR_SIZE
                        current_aggregated_writes_bytes += sectors_written * SECTOR_SIZE
                    except ValueError:
                        print(f"Aviso: Não foi possível parsear dados de I/O para o dispositivo {device_name}")
                        continue
    except (FileNotFoundError, IndexError) as e:
        print(f"Erro ao leer ou processar /proc/diskstats: {e}")

    # Calcula as taxas de I/O (bytes por segundo) usando a diferença entre as leituras.
    elapsed_disk_io_time = current_timestamp - cache.get('prev_disk_io_timestamp', current_timestamp - 1.0)
    if elapsed_disk_io_time <= 0.001: elapsed_disk_io_time = 1.0

    prev_total_reads_bytes = cache.get('prev_disk_stats', {}).get('total_reads_bytes', current_aggregated_reads_bytes)
    prev_total_writes_bytes = cache.get('prev_disk_stats', {}).get('total_writes_bytes', current_aggregated_writes_bytes)

    if cache.get('prev_disk_io_timestamp', current_timestamp) < (current_timestamp - 0.1) :
        read_diff_bytes = current_aggregated_reads_bytes - prev_total_reads_bytes
        write_diff_bytes = current_aggregated_writes_bytes - prev_total_writes_bytes
        disk_read_bps = read_diff_bytes / elapsed_disk_io_time
        disk_write_bps = write_diff_bytes / elapsed_disk_io_time

    # Atualiza o cache de I/O do disco.
    cache['prev_disk_stats'] = {
        'total_reads_bytes': current_aggregated_reads_bytes,
        'total_writes_bytes': current_aggregated_writes_bytes,
    }
    cache['prev_disk_io_timestamp'] = current_timestamp

    # Retorna um dicionário com todas as informações globais coletadas e processadas.
    return {
        "CPU (%)": round(cpu_used_pct, 2),
        "CPU ocioso (%)": round(cpu_ocioso_pct, 2),
        "Memória Usada (KB)": mem_used_absolute_kb,
        "Memória (%)": round(mem_used_pct, 2),
        "Memória Livre (%)": round(mem_free_pct, 2),
        "Total de Processos": proc_count,
        "Total de Threads": thread_count_global,
        "Leitura Disco (B/s)": round(max(0, disk_read_bps), 2),
        "Escrita Disco (B/s)": round(max(0, disk_write_bps), 2)
    }

def get_processes_info(limit=10):
    """
    Coleta informações sobre os processos em execução no sistema.
    Lê dados de /proc/[pid]/stat (tempos de CPU, nome), /proc/[pid]/status (UID, VmRSS, Threads)
    e /proc/[pid]/io (bytes lidos/escritos pelo processo).
    Calcula o uso percentual de CPU, uso de memória (MB e %), e taxas de I/O para cada processo.
    Ordena os processos por tempo de CPU total acumulado (o maior primeiro) e
    retorna um número limitado de processos conforme o argumento `limit`.

    Args:
        limit (int): O número máximo de processos a serem retornados na lista.

    Returns:
        list: Uma lista de dicionários, onde cada dicionário representa um processo e
              suas informações (PID, nome, usuário, %CPU, memória, etc.).
              Ex: [{'pid': 1, 'name': 'systemd', 'cpu_percent': 0.1, ...}, ...]
    """
    global cache, CLK_TCK
    processes = []

    now = time.time()
    # Calcula o tempo de parede decorrido para normalizar métricas.
    elapsed_wall_time = now - cache.get('prev_timestamp', now - 1.0)
    if elapsed_wall_time <= 0.001: elapsed_wall_time = 1.0

    # Garante que o total de memória RAM esteja no cache para cálculos de porcentagem.
    if cache['mem_total_kb'] is None:
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        cache['mem_total_kb'] = int(line.split()[1])
                        break
        except (FileNotFoundError, ValueError):
            cache['mem_total_kb'] = 1

    mem_total_kb = cache.get('mem_total_kb', 1)
    if mem_total_kb == 0: mem_total_kb = 1

    active_pids_this_run = set() # Rastreia PIDs ativos nesta execução para limpeza do cache.

    # Itera sobre os diretórios de processo em /proc.
    for proc_dir in Path('/proc').iterdir():
        if not (proc_dir.is_dir() and proc_dir.name.isdigit()): continue

        pid_str = proc_dir.name
        pid_val = int(pid_str)
        active_pids_this_run.add(pid_str)

        try:
            # --- Leitura de /proc/[pid]/stat para tempo de CPU e nome ---
            with open(proc_dir / 'stat', 'r') as sf:
                vals = sf.readline().split()

            name = vals[1].strip('()')
            utime_ticks = int(vals[13])
            stime_ticks = int(vals[14])
            current_proc_total_ticks = utime_ticks + stime_ticks

            # --- Leitura de /proc/[pid]/status para UID, memória e threads ---
            uid_int = -1
            mem_kb_val = 0
            num_threads = 0
            try:
                with open(proc_dir / 'status', 'r') as sf_status:
                    for line in sf_status:
                        if line.startswith('Uid:'): uid_int = int(line.split()[1])
                        elif line.startswith('VmRSS:'):
                            mem_kb_str = line.split()[1]
                            mem_kb_val = int(mem_kb_str) if mem_kb_str.isdigit() else 0
                        elif line.startswith('Threads:'): num_threads = int(line.split()[1])
            except FileNotFoundError:
                # Se o processo sumiu, remove do cache e pula.
                if pid_str in cache['prev_times']: del cache['prev_times'][pid_str]
                if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str]
                continue

            username = get_username_from_uid_local(uid_int) if uid_int != -1 else 'N/A'

            # --- Cálculo da porcentagem de CPU usada pelo processo ---
            prev_proc_ticks = cache['prev_times'].get(pid_str, 0)
            cpu_time_diff_seconds = (current_proc_total_ticks - prev_proc_ticks) / CLK_TCK
            cpu_pct = (cpu_time_diff_seconds / elapsed_wall_time) * 100

            # --- Cálculo do uso de memória pelo processo ---
            mem_mb = mem_kb_val / 1024.0
            mem_pct = (mem_kb_val / mem_total_kb) * 100.0 if mem_total_kb > 0 else 0.0

            cpu_time_seconds = current_proc_total_ticks / CLK_TCK

            # Atualiza o cache de ticks de CPU do processo.
            cache['prev_times'][pid_str] = current_proc_total_ticks

            # --- Cálculo de I/O por processo (leitura de /proc/[pid]/io) ---
            io_read_bps = 0.0
            io_write_bps = 0.0
            try:
                with open(proc_dir / 'io', 'r') as f_io:
                    current_proc_read_bytes = 0
                    current_proc_write_bytes = 0
                    for line in f_io:
                        if line.startswith('read_bytes:'): current_proc_read_bytes = int(line.split()[1])
                        elif line.startswith('write_bytes:'): current_proc_write_bytes = int(line.split()[1])

                prev_io_stats_for_pid = cache['prev_proc_io_stats'].get(pid_str)
                if prev_io_stats_for_pid:
                    read_bytes_diff = current_proc_read_bytes - prev_io_stats_for_pid['read_bytes']
                    write_bytes_diff = current_proc_write_bytes - prev_io_stats_for_pid['write_bytes']
                    io_read_bps = read_bytes_diff / elapsed_wall_time if elapsed_wall_time > 0 else 0
                    io_write_bps = write_bytes_diff / elapsed_wall_time if elapsed_wall_time > 0 else 0

                # Atualiza o cache de I/O do processo.
                cache['prev_proc_io_stats'][pid_str] = {
                    'read_bytes': current_proc_read_bytes,
                    'write_bytes': current_proc_write_bytes,
                }
            except (FileNotFoundError, PermissionError, ValueError):
                pass # Ignora se o arquivo não existe ou não tem permissão.

            processes.append({
                'pid': pid_val,
                'name': name,
                'username': username,
                'threads': num_threads,
                'cpu_percent': round(max(0, cpu_pct), 2),
                'memory_mb': round(mem_mb, 2),
                'memory_percent': round(mem_pct, 2),
                'cpu_time': round(cpu_time_seconds, 2),
                'io_read_bps': round(max(0, io_read_bps), 2),
                'io_write_bps': round(max(0, io_write_bps), 2)
            })

        except FileNotFoundError:
            # Limpa o cache se o processo desapareceu.
            if pid_str in cache['prev_times']: del cache['prev_times'][pid_str]
            if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str]
            continue
        except (PermissionError, IndexError, ValueError) as e:
            print(f"Erro ao processar dados básicos do PID {pid_str}: {e}")
            # Limpa o cache em caso de erro na leitura.
            if pid_str in cache['prev_times']: del cache['prev_times'][pid_str]
            if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str]
            continue
        except Exception as e:
            print(f"Erro inesperado ao processar PID {pid_str}: {e}")
            # Limpa o cache em caso de erro genérico.
            if pid_str in cache['prev_times']: del cache['prev_times'][pid_str]
            if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str]
            continue

    # --- Limpeza do cache: remove PIDs de processos que não existem mais ---
    # Identifica e remove do cache PIDs que não foram encontrados na varredura atual.
    stale_cpu_pids = set(cache['prev_times'].keys()) - active_pids_this_run
    for stale_pid in stale_cpu_pids:
        if stale_pid in cache['prev_times']: del cache['prev_times'][stale_pid]

    stale_io_pids = set(cache['prev_proc_io_stats'].keys()) - active_pids_this_run
    for stale_pid in stale_io_pids:
        if stale_pid in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][stale_pid]

    # Atualiza o timestamp da última coleta de processos.
    cache['prev_timestamp'] = now

    # Ordena os processos pelo tempo de CPU acumulado e limita a lista.
    processes.sort(key=lambda x: x.get('cpu_time', 0), reverse=True)
    return processes[:limit]

def _parse_kb_value_from_status_line(value_str_with_unit):
    """
    Função auxiliar para converter uma string de memória (ex: '  123 kB')
    lida do arquivo /proc/[pid]/status para um valor inteiro em Kilobytes (KB).
    """
    if isinstance(value_str_with_unit, str) and "kb" in value_str_with_unit.lower():
        try:
            return int(value_str_with_unit.lower().replace("kb", "").strip())
        except ValueError:
            return 0
    return 0

def get_process_open_files(pid):
    """
    Lista os arquivos e descritores de arquivo abertos por um processo específico.
    Lê o diretório /proc/[pid]/fd, que contém links simbólicos para os arquivos abertos.
    Tenta resolver esses links para obter o caminho real do arquivo.
    Identifica o tipo de recurso (arquivo, pipe, socket, etc.).

    Args:
        pid (int): O ID do processo.

    Returns:
        list: Uma lista de dicionários, onde cada dicionário representa um recurso aberto.
              Ex: [{'fd': '0', 'path': '/dev/null', 'type': 'file'}, ...]
              Retorna uma lista vazia em caso de erro ou se o diretório não existir.
    """
    open_files = []
    fd_dir = Path(f"/proc/{pid}/fd") # Caminho para o diretório de descritores de arquivo do processo.

    if not fd_dir.is_dir(): return open_files # Retorna vazio se o diretório não existe.

    try:
        for fd_entry in fd_dir.iterdir(): # Itera sobre as entradas no diretório /proc/[pid]/fd.
            try:
                fd = fd_entry.name # O nome da entrada é o número do descritor de arquivo.
                real_path = os.readlink(str(fd_entry)) # Resolve o link simbólico para o caminho real.

                # Determina o tipo de recurso com base no caminho real.
                resource_type = "arquivo"
                if real_path.startswith("socket:"): resource_type = "socket"
                elif real_path.startswith("pipe:"): resource_type = "pipe"
                elif real_path.startswith("anon_inode:"): resource_type = "inode anônimo"
                elif real_path.startswith("/dev/"): resource_type = "dispositivo"
                elif real_path == "/": resource_type = "diretório raiz"
                elif Path(real_path).is_dir(): resource_type = "diretório"
                elif Path(real_path).is_fifo(): resource_type = "FIFO (pipe nomeado)"
                elif Path(real_path).is_socket(): resource_type = "socket (filesystem)"
                elif Path(real_path).is_symlink(): resource_type = "link simbólico"

                open_files.append({
                    'fd': fd,
                    'path': real_path,
                    'type': resource_type
                })
            except FileNotFoundError: continue # Recurso pode ter sido fechado.
            except PermissionError:
                open_files.append({
                    'fd': fd_entry.name,
                    'path': '[Permissão Negada]',
                    'type': 'Desconhecido'
                })
            except Exception as e:
                print(f"Aviso: Erro ao ler FD {fd_entry.name} para PID {pid}: {e}")
                open_files.append({
                    'fd': fd_entry.name,
                    'path': '[Erro ao Ler]',
                    'type': 'Desconhecido'
                })
    except PermissionError:
        print(f"Erro de permissão: Não foi possível listar FDs para PID {pid}.")
    except Exception as e:
        print(f"Erro inesperado ao obter arquivos abertos para PID {pid}: {e}")

    return open_files # Retorna a lista de recursos abertos.


def get_process_details(pid):
    """
    Obtém informações detalhadas para um processo específico, dado seu PID.
    Lê principalmente de /proc/[pid]/status para a maioria dos detalhes e complementa
    com informações de /proc/[pid]/stat (como 'nice', tempo de início, tempos de CPU).
    Também calcula o número de páginas de memória com base nos valores de VmRSS, VmSize, etc.
    Inclui informações sobre arquivos e dispositivos abertos pelo processo.

    Args:
        pid (int): O ID do processo para o qual obter detalhes.

    Returns:
        dict or None: Um dicionário com os detalhes do processo se encontrado e legível.
                      Retorna `None` se o processo com o PID especificado não for encontrado
                      ou se ocorrer um erro significativo ao ler seus dados.
    """
    global CLK_TCK, PAGE_SIZE
    try:
        proc_path = Path(f'/proc/{pid}')
        if not proc_path.exists(): return None

        # --- Leitura de /proc/[pid]/status para detalhes gerais e de memória ---
        status_content = {}
        try:
            with open(proc_path / 'status', 'r') as f:
                for line in f:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        status_content[parts[0].strip()] = parts[1].strip()
        except FileNotFoundError: return None
        except Exception as e:
            print(f"Erro ao ler /proc/{pid}/status para PID {pid}: {e}")
            return None

        name_val = status_content.get('Name', 'N/A')
        raw_state_val = status_content.get('State', 'N/A')
        uid_str_val = status_content.get('Uid', 'N/A N/A N/A N/A').split()[0]
        username_val = get_username_from_uid_local(int(uid_str_val)) if uid_str_val.isdigit() else 'N/A'
        threads_in_details = status_content.get('Threads', 'N/A')

        # --- Leitura de /proc/[pid]/stat para tempo de CPU, nice e tempo de início ---
        nice_val_from_stat = "N/A"
        start_ticks_after_boot_val = "N/A"
        utime_ticks_val = 0
        stime_ticks_val = 0
        try:
            with open(proc_path / 'stat', 'r') as f_stat:
                stat_vals = f_stat.read().split()
            utime_ticks_val = int(stat_vals[13])
            stime_ticks_val = int(stat_vals[14])
            nice_val_from_stat = int(stat_vals[18])
            start_ticks_after_boot_val = int(stat_vals[21])
        except (FileNotFoundError, IndexError, ValueError) as e:
            print(f"Aviso: Não foi possível ler alguns campos de /proc/{pid}/stat: {e}")

        translated_priority_val = _translate_priority_from_nice(nice_val_from_stat if isinstance(nice_val_from_stat, int) else None)
        cpu_time_seconds = round((utime_ticks_val + stime_ticks_val) / CLK_TCK, 2)

        # --- Calcula o horário de início do processo ---
        process_start_str = "N/A"
        system_boot_time_epoch = 0
        if isinstance(start_ticks_after_boot_val, int):
            try:
                with open('/proc/stat', 'r') as f_sys_stat:
                    for line in f_sys_stat:
                        if line.startswith('btime'):
                            system_boot_time_epoch = int(line.split()[1])
                            break
            except (FileNotFoundError, ValueError) as e:
                print(f"Aviso: Não foi possível ler o tempo de boot do sistema: {e}")

            if system_boot_time_epoch > 0:
                process_start_epoch = system_boot_time_epoch + (start_ticks_after_boot_val / CLK_TCK)
                process_start_str = datetime.fromtimestamp(process_start_epoch).strftime('%d/%m/%Y %H:%M:%S')
            else:
                process_start_str = f"{(start_ticks_after_boot_val / CLK_TCK):.2f}s após o boot"

        # --- Informações de memória do processo (de /proc/[pid]/status) ---
        vm_rss_str = status_content.get('VmRSS', '0 kB')
        vm_size_str = status_content.get('VmSize', '0 kB')
        rss_shmem_str = status_content.get('RssShmem', '0 kB')

        # Converte strings de KB para inteiros para cálculos.
        vm_rss_kb = _parse_kb_value_from_status_line(vm_rss_str)
        vm_size_kb = _parse_kb_value_from_status_line(vm_size_str)
        vm_exe_kb = _parse_kb_value_from_status_line(status_content.get('VmExe', '0 kB'))
        vm_data_kb = _parse_kb_value_from_status_line(status_content.get('VmData', '0 kB'))
        vm_stk_kb = _parse_kb_value_from_status_line(status_content.get('VmStk', '0 kB'))

        # Calcula o número de páginas de memória para diferentes segmentos.
        total_pages_resident = int(vm_rss_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'
        total_pages_virtual = int(vm_size_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'
        code_pages = int(vm_exe_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'
        data_heap_pages = int(vm_data_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'
        stack_pages = int(vm_stk_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'

        vm_data_str = status_content.get('VmData', '0 kB')

        # --- Coleta informações sobre arquivos e recursos abertos ---
        open_files_and_resources = get_process_open_files(pid)

        # Retorna o dicionário completo de detalhes do processo.
        details_to_return = {
            'PID': pid,
            'Nome': name_val,
            'Usuário': username_val,
            'Estado': raw_state_val,
            'Número de Threads': threads_in_details,

            'Memória Residente (VmRSS)': vm_rss_str,
            'Memória Virtual (VmSize)': vm_size_str,

            'Páginas Totais Residente': total_pages_resident,
            'Páginas Totais Virtual': total_pages_virtual,
            'Páginas de Código (VmExe)': code_pages,
            'Páginas de Dados/Heap (VmData)': data_heap_pages,
            'Páginas de Stack (VmStk)': stack_pages,

            'Memória Compartilhada (RssShmem)': rss_shmem_str,
            'Memória Gravável (VmData)': vm_data_str,

            'Tempo da CPU (s)': cpu_time_seconds,
            'Iniciado': process_start_str,
            'Prioridade': translated_priority_val,
            'Nice': nice_val_from_stat,
            'Recursos Abertos': open_files_and_resources
        }
        return details_to_return

    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Erro inesperado ao obter detalhes para PID {pid}: {e}")
        return None

def _translate_priority_from_nice(nice_value):
    """
    Converte um valor 'nice' numérico (de -20 a 19) para uma descrição textual da prioridade do processo.
    Valores 'nice' em Linux:
      -20: Maior prioridade para o processo (mais favorecido pelo scheduler).
        0: Prioridade padrão/normal.
       19: Menor prioridade para o processo (menos favorecido).
    """
    if not isinstance(nice_value, int): return "N/A"
    if nice_value <= -15: return "Muito Alta"
    elif nice_value <= -1: return "Alta"
    elif nice_value == 0: return "Normal"
    elif nice_value <= 10: return "Baixa"
    elif nice_value <= 19: return "Muito Baixa"
    else: return "Desconhecida"