# model.py

import time
from pathlib import Path
from datetime import datetime

# O módulo 'os' (exceto o que pathlib pode usar internamente) e 'pwd'
# não são importados intencionalmente, conforme os requisitos.

# Cache global para armazenar dados de chamadas anteriores,
# permitindo o cálculo de métricas baseadas em diferenças (como % CPU, taxas de I/O).
cache = {
    'prev_times': {},  # Armazena os últimos tempos de CPU (utime + stime) para cada PID. Usado para calcular % CPU do processo.
    'prev_sys_cpu_times': {}, # Armazena os últimos tempos de CPU do sistema (user, nice, system, idle, etc.). Usado para calcular % CPU global.
    'prev_timestamp': time.time(), # Timestamp da última coleta de dados de processos. Usado para calcular deltas de tempo.
    'mem_total_kb': None, # Cache para o total de memória RAM em KB. Evita releituras constantes do /proc/meminfo.
    'swap_total_kb': None, # Cache para o total de memória Swap em KB. (Atualmente não usado na view, mas coletado).
    'prev_disk_stats': {}, # Armazena as últimas estatísticas de I/O do disco (total_reads_bytes, total_writes_bytes).
    'prev_disk_io_timestamp': time.time(), # Timestamp da última coleta de I/O de disco.
    'prev_proc_io_stats': {}, # Cache para estatísticas de I/O por processo (read_bytes, write_bytes).
}

# Constantes do sistema.
CLK_TCK = 100  # Clock ticks por segundo, padrão em muitos sistemas Linux. Usado para converter jiffies para segundos.
PAGE_SIZE = 4096  # Tamanho da página de memória em bytes (comum em x86). Usado para calcular o número de páginas.
SECTOR_SIZE = 512 # Tamanho de um setor de disco em bytes. Usado para calcular bytes lidos/escritos de /proc/diskstats.

_user_cache = {} # Cache para mapeamento de UID para nome de usuário, para evitar leituras repetidas de /etc/passwd.

def get_username_from_uid_local(uid_int):
    """
    Obtém o nome de usuário correspondente a um UID (User ID) lendo o arquivo /etc/passwd.
    Utiliza um cache interno para otimizar chamadas repetidas para o mesmo UID.

    Args:
        uid_int (int): O ID do usuário.

    Returns:
        str: O nome de usuário correspondente ou o UID como string se não encontrado ou em caso de erro.
    """
    if uid_int in _user_cache:
        return _user_cache[uid_int]
    try:
        with open('/etc/passwd', 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) > 2: # Formato básico do /etc/passwd: nome:senha_cript:UID:GID:...
                    try:
                        if int(parts[2]) == uid_int: # Compara o UID da linha com o UID procurado
                            _user_cache[uid_int] = parts[0] # Armazena no cache e retorna o nome de usuário
                            return parts[0]
                    except ValueError:
                        # Ignora linhas onde o UID não é um número válido
                        continue
    except FileNotFoundError:
        # Se /etc/passwd não for encontrado, retorna o UID como string e armazena no cache
        _user_cache[uid_int] = str(uid_int)
        return str(uid_int)
    # Se o UID não for encontrado no arquivo, retorna o UID como string e armazena no cache
    _user_cache[uid_int] = str(uid_int)
    return str(uid_int)

def get_global_info():
    """
    Coleta informações globais do sistema, como uso de CPU, memória, swap,
    contagem de processos/threads e taxas de I/O de disco.
    Utiliza o cache global para calcular métricas baseadas em diferenças de tempo.

    Returns:
        dict: Um dicionário contendo as informações globais do sistema.
    """
    global cache
    current_timestamp = time.time() # Timestamp atual para cálculos de taxa

    cpu_used_pct = 0.0
    cpu_idle_pct = 0.0
    try:
        # Lê /proc/stat para informações de tempo da CPU
        with open('/proc/stat', 'r') as f:
            line = f.readline() # A primeira linha contém os tempos agregados da CPU
            fields = list(map(int, line.split()[1:])) # user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice
        
        # Calcula o tempo ocioso atual e o tempo total atual
        current_idle = fields[3] + fields[4]  # idle + iowait
        current_total = sum(fields)
        
        # Obtém os valores anteriores do cache
        prev_idle = cache['prev_sys_cpu_times'].get('idle', 0)
        prev_total = cache['prev_sys_cpu_times'].get('total', 0)

        if prev_total > 0 and current_total > prev_total: # Se houver dados anteriores válidos
            total_diff = current_total - prev_total
            idle_diff = current_idle - prev_idle
            # Calcula a porcentagem de uso e ociosidade da CPU com base na diferença
            cpu_used_pct = (1.0 - (idle_diff / total_diff)) * 100 if total_diff > 0 else 0.0
            cpu_idle_pct = (idle_diff / total_diff) * 100 if total_diff > 0 else 0.0
        else: # Caso seja a primeira leitura ou não haja diferença significativa (raro)
            non_idle_time = fields[0] + fields[1] + fields[2] + fields[5] + fields[6] + fields[7] # user + nice + system + irq + softirq + steal
            cpu_used_pct = (non_idle_time / current_total) * 100 if current_total > 0 else 0.0
            cpu_idle_pct = (fields[3] / current_total * 100) if current_total > 0 else 0.0
        
        # Atualiza o cache com os valores atuais para o próximo cálculo
        cache['prev_sys_cpu_times']['idle'] = current_idle
        cache['prev_sys_cpu_times']['total'] = current_total
    except (FileNotFoundError, IndexError, ValueError, ZeroDivisionError) as e: # pragma: no cover
        print(f"Erro ao ler /proc/stat: {e}")

    # Inicialização de variáveis de memória e swap
    mem_used_pct = 0.0
    mem_free_pct = 0.0
    mem_used_absolute_kb = 0
    swap_total_kb_val = 0
    swap_used_kb_val = 0
    swap_used_pct_val = 0.0

    try:
        # Lê /proc/meminfo para informações de memória
        meminfo = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                k, v = line.split(':', 1)
                meminfo[k.strip()] = int(v.split()[0]) # Armazena chave e valor (em KB)
        
        total_mem_kb = meminfo.get('MemTotal', 1) # Pega MemTotal, ou 1 para evitar divisão por zero
        # MemAvailable é uma estimativa mais precisa da memória disponível para novas aplicações sem swapping
        avail_mem_kb = meminfo.get('MemAvailable', meminfo.get('MemFree', 0)) 
        
        # Atualiza o cache de memória total se for a primeira vez ou se mudou (improvável, mas seguro)
        if cache['mem_total_kb'] is None or cache['mem_total_kb'] != total_mem_kb: # pragma: no cover
             cache['mem_total_kb'] = total_mem_kb
        
        if total_mem_kb > 0:
            mem_used_pct = (1.0 - (avail_mem_kb / total_mem_kb)) * 100
            mem_free_pct = (avail_mem_kb / total_mem_kb) * 100
            mem_used_absolute_kb = total_mem_kb - avail_mem_kb
        else: # pragma: no cover
            mem_used_pct = 0.0
            mem_free_pct = 0.0
            mem_used_absolute_kb = 0

        # Coleta de informações de Swap
        swap_total_kb_val = meminfo.get('SwapTotal', 0)
        swap_free_kb = meminfo.get('SwapFree', 0)
        # Atualiza o cache de swap total (pode não ser usado na view atual, mas é coletado)
        if cache['swap_total_kb'] is None or cache['swap_total_kb'] != swap_total_kb_val: # pragma: no cover
            cache['swap_total_kb'] = swap_total_kb_val
        
        if swap_total_kb_val > 0:
            swap_used_kb_val = swap_total_kb_val - swap_free_kb
            swap_used_pct_val = (swap_used_kb_val / swap_total_kb_val) * 100
        else: # pragma: no cover
            swap_used_kb_val = 0
            swap_used_pct_val = 0.0

    except (FileNotFoundError, ValueError, ZeroDivisionError) as e: # pragma: no cover
        print(f"Erro ao ler /proc/meminfo: {e}")
        # Define valores padrão em caso de erro para manter a estrutura do retorno
        mem_used_pct = 0.0
        mem_free_pct = 0.0
        mem_used_absolute_kb = 0
        swap_total_kb_val = 0
        swap_used_kb_val = 0
        swap_used_pct_val = 0.0

    # Contagem de processos e threads totais no sistema
    proc_count = 0
    thread_count_global = 0
    for proc_dir_global in Path('/proc').iterdir(): # Itera sobre os diretórios em /proc
        if proc_dir_global.is_dir() and proc_dir_global.name.isdigit(): # Verifica se é um diretório de PID
            proc_count += 1
            try:
                # Lê o arquivo de status do processo para obter o número de threads
                with open(proc_dir_global / 'status', 'r') as sf_global:
                    for line_global in sf_global:
                        if line_global.startswith('Threads:'):
                            thread_count_global += int(line_global.split()[1])
                            break
            except (FileNotFoundError, PermissionError, ValueError): # pragma: no cover
                # Ignora processos que podem ter sumido ou não ter permissão de leitura
                continue
    
    # Cálculo de I/O de Disco (leitura e escrita por segundo)
    disk_read_bps = 0.0
    disk_write_bps = 0.0
    current_aggregated_reads_bytes = 0
    current_aggregated_writes_bytes = 0
    # Lista de prefixos de dispositivos de bloco relevantes (ex: sda, hda, vda, xvda)
    relevant_device_prefixes = ('sd', 'hd', 'vd', 'xvd')
    nvme_prefix = 'nvme' # Prefixo para dispositivos NVMe
    try:
        with open('/proc/diskstats', 'r') as f:
            for line in f:
                fields = line.split()
                if len(fields) < 10: continue # Linhas válidas têm pelo menos 10 campos
                device_name = fields[2]
                is_relevant = False
                # Verifica se o dispositivo é um disco principal (e não uma partição)
                for prefix in relevant_device_prefixes:
                    if device_name.startswith(prefix):
                        # Considera relevante se não houver dígitos após o prefixo (ex: sda, não sda1)
                        if not any(char.isdigit() for char in device_name[len(prefix):]):
                            is_relevant = True
                        break
                if not is_relevant and device_name.startswith(nvme_prefix): # pragma: no cover
                    # Para NVMe, considera relevante se não for uma partição (ex: nvme0n1, não nvme0n1p1)
                    if 'p' not in device_name[len(nvme_prefix):]:
                        is_relevant = True
                # Ignora dispositivos como CD-ROM, loopback, RAM disks, device mapper
                if device_name.startswith(('sr', 'loop', 'ram', 'dm-')): # pragma: no cover
                    is_relevant = False
                
                if is_relevant:
                    try:
                        sectors_read = int(fields[5]) # Campo 6: setores lidos
                        sectors_written = int(fields[9]) # Campo 10: setores escritos
                        current_aggregated_reads_bytes += sectors_read * SECTOR_SIZE
                        current_aggregated_writes_bytes += sectors_written * SECTOR_SIZE
                    except ValueError: # pragma: no cover
                        print(f"Aviso: Não foi possível parsear dados de I/O para o dispositivo {device_name}")
                        continue
    except (FileNotFoundError, IndexError) as e: # pragma: no cover
        print(f"Erro ao ler ou processar /proc/diskstats: {e}")

    # Calcula o tempo decorrido desde a última medição de I/O de disco
    elapsed_disk_io_time = current_timestamp - cache.get('prev_disk_io_timestamp', current_timestamp - 1.0)
    if elapsed_disk_io_time <= 0.001: # pragma: no cover Evita divisão por zero ou valores irreais
        elapsed_disk_io_time = 1.0
    
    # Obtém os valores anteriores de I/O do cache
    prev_total_reads_bytes = cache.get('prev_disk_stats', {}).get('total_reads_bytes', current_aggregated_reads_bytes)
    prev_total_writes_bytes = cache.get('prev_disk_stats', {}).get('total_writes_bytes', current_aggregated_writes_bytes)

    # Calcula as taxas de I/O se houver um intervalo de tempo razoável desde a última medição
    if cache.get('prev_disk_io_timestamp') < (current_timestamp - 0.1) :
        read_diff_bytes = current_aggregated_reads_bytes - prev_total_reads_bytes
        write_diff_bytes = current_aggregated_writes_bytes - prev_total_writes_bytes
        disk_read_bps = read_diff_bytes / elapsed_disk_io_time
        disk_write_bps = write_diff_bytes / elapsed_disk_io_time
    # else: Se o tempo for muito curto, as taxas permanecem 0.0 ou o valor anterior se não resetadas

    # Atualiza o cache com as estatísticas de I/O e o timestamp atuais
    cache['prev_disk_stats'] = {
        'total_reads_bytes': current_aggregated_reads_bytes,
        'total_writes_bytes': current_aggregated_writes_bytes,
    }
    cache['prev_disk_io_timestamp'] = current_timestamp

    # Retorna um dicionário com todas as informações globais coletadas e processadas
    return {
        "CPU (%)": round(cpu_used_pct, 2),
        "CPU ocioso (%)": round(cpu_idle_pct, 2),
        "Memória Usada (KB)": mem_used_absolute_kb,
        "Memória (%)": round(mem_used_pct, 2),
        "Memória Livre (%)": round(mem_free_pct, 2),
        "Swap Total (KB)": swap_total_kb_val,       # Informação de Swap (Total)
        "Swap Usada (KB)": swap_used_kb_val,        # Informação de Swap (Usada)
        "Swap Usada (%)": round(swap_used_pct_val, 2), # Informação de Swap (Percentual)
        "Total de Processos": proc_count,
        "Total de Threads": thread_count_global,
        "Leitura Disco (B/s)": round(max(0, disk_read_bps), 2), # Garante que não seja negativo
        "Escrita Disco (B/s)": round(max(0, disk_write_bps), 2) # Garante que não seja negativo
    }

def get_processes_info(limit=10):
    """
    Coleta informações sobre os processos em execução no sistema.
    Lê dados de /proc/[pid]/stat, /proc/[pid]/status e /proc/[pid]/io.
    Calcula uso de CPU, memória e I/O para cada processo.
    Ordena os processos por tempo de CPU e retorna um número limitado de processos.

    Args:
        limit (int): O número máximo de processos a serem retornados.

    Returns:
        list: Uma lista de dicionários, cada um representando um processo e suas informações.
    """
    global cache, CLK_TCK
    processes = [] # Lista para armazenar informações dos processos
    
    now = time.time() # Timestamp atual
    # Calcula o tempo decorrido desde a última chamada desta função
    elapsed_wall_time = now - cache.get('prev_timestamp', now - 1.0) # Fallback para 1 segundo se for a primeira vez
    if elapsed_wall_time <= 0.001: # pragma: no cover Evita divisão por zero ou taxas inflacionadas
        elapsed_wall_time = 1.0

    # Garante que 'mem_total_kb' no cache esteja populado, se ainda não estiver
    if cache['mem_total_kb'] is None: # pragma: no cover
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        cache['mem_total_kb'] = int(line.split()[1])
                        break
        except (FileNotFoundError, ValueError):
            cache['mem_total_kb'] = 1 # Fallback para evitar divisão por zero

    mem_total_kb = cache.get('mem_total_kb', 1)
    if mem_total_kb == 0: mem_total_kb = 1 # pragma: no cover Evita divisão por zero

    active_pids_this_run = set() # Conjunto para rastrear PIDs ativos nesta execução

    # Itera sobre os diretórios em /proc
    for proc_dir in Path('/proc').iterdir():
        # Verifica se o diretório é numérico (representando um PID)
        if not (proc_dir.is_dir() and proc_dir.name.isdigit()):
            continue
        
        pid_str = proc_dir.name
        pid_val = int(pid_str)
        active_pids_this_run.add(pid_str) # Adiciona PID ao conjunto de ativos
        
        try:
            # Lê /proc/[pid]/stat para informações de CPU e nome do processo
            with open(proc_dir / 'stat', 'r') as sf:
                vals = sf.readline().split()
            name = vals[1].strip('()') # Nome do processo (campo 2)
            utime_ticks = int(vals[13]) # Tempo de CPU em modo usuário (campo 14)
            stime_ticks = int(vals[14]) # Tempo de CPU em modo kernel (campo 15)
            current_proc_total_ticks = utime_ticks + stime_ticks # Tempo total de CPU do processo

            # Inicializa variáveis para dados do /proc/[pid]/status
            uid_int = -1
            mem_kb_val = 0
            num_threads = 0
            try:
                # Lê /proc/[pid]/status para UID, VmRSS e número de Threads
                with open(proc_dir / 'status', 'r') as sf_status:
                    for line in sf_status:
                        if line.startswith('Uid:'):
                            uid_int = int(line.split()[1]) # UID real
                        elif line.startswith('VmRSS:'):
                            mem_kb_str = line.split()[1]
                            mem_kb_val = int(mem_kb_str) if mem_kb_str.isdigit() else 0 # Memória Residente
                        elif line.startswith('Threads:'):
                            num_threads = int(line.split()[1]) # Número de threads
            except FileNotFoundError: # pragma: no cover (processo pode ter terminado)
                # Remove dados do cache se o processo sumiu
                if pid_str in cache['prev_times']: del cache['prev_times'][pid_str]
                if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str]
                continue

            username = get_username_from_uid_local(uid_int) if uid_int != -1 else 'N/A' # Obtém nome de usuário
            
            # Cálculo da porcentagem de CPU usada pelo processo
            prev_proc_ticks = cache['prev_times'].get(pid_str, 0) # Ticks da leitura anterior
            cpu_time_diff_seconds = (current_proc_total_ticks - prev_proc_ticks) / CLK_TCK
            cpu_pct = (cpu_time_diff_seconds / elapsed_wall_time) * 100
            
            # Cálculo do uso de memória
            mem_mb = mem_kb_val / 1024.0
            mem_pct = (mem_kb_val / mem_total_kb) * 100.0 if mem_total_kb > 0 else 0.0
            
            cpu_time_seconds = current_proc_total_ticks / CLK_TCK # Tempo total de CPU em segundos
            
            # Armazena os ticks atuais para o próximo cálculo
            cache['prev_times'][pid_str] = current_proc_total_ticks
            
            # Cálculo de I/O por processo
            io_read_bps = 0.0
            io_write_bps = 0.0
            try:
                # Lê /proc/[pid]/io para bytes lidos e escritos
                with open(proc_dir / 'io', 'r') as f_io:
                    current_proc_read_bytes = 0
                    current_proc_write_bytes = 0
                    for line in f_io:
                        if line.startswith('read_bytes:'):
                            current_proc_read_bytes = int(line.split()[1])
                        elif line.startswith('write_bytes:'):
                            current_proc_write_bytes = int(line.split()[1])
                
                prev_io_stats_for_pid = cache['prev_proc_io_stats'].get(pid_str)
                if prev_io_stats_for_pid: # Se houver dados de I/O anteriores para este PID
                    read_bytes_diff = current_proc_read_bytes - prev_io_stats_for_pid['read_bytes']
                    write_bytes_diff = current_proc_write_bytes - prev_io_stats_for_pid['write_bytes']
                    # Calcula as taxas de I/O em bytes por segundo
                    io_read_bps = read_bytes_diff / elapsed_wall_time if elapsed_wall_time > 0 else 0
                    io_write_bps = write_bytes_diff / elapsed_wall_time if elapsed_wall_time > 0 else 0
                
                # Atualiza o cache de I/O do processo
                cache['prev_proc_io_stats'][pid_str] = {
                    'read_bytes': current_proc_read_bytes,
                    'write_bytes': current_proc_write_bytes,
                }
            except (FileNotFoundError, PermissionError, ValueError): # pragma: no cover
                # Ignora erros de leitura de I/O (ex: processo kernel, permissões)
                pass

            # Adiciona as informações do processo à lista
            processes.append({
                'pid': pid_val,
                'name': name,
                'username': username,
                'threads': num_threads,
                'cpu_percent': round(max(0, cpu_pct), 2), # Garante que não seja negativo
                'memory_mb': round(mem_mb, 2),
                'memory_percent': round(mem_pct, 2),
                'cpu_time': round(cpu_time_seconds, 2),
                'io_read_bps': round(max(0, io_read_bps), 2), # Garante que não seja negativo
                'io_write_bps': round(max(0, io_write_bps), 2) # Garante que não seja negativo
            })
            
        except FileNotFoundError: # pragma: no cover (processo terminou durante a coleta)
            if pid_str in cache['prev_times']: del cache['prev_times'][pid_str]
            if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str]
            continue
        except (PermissionError, IndexError, ValueError) as e: # pragma: no cover
            print(f"Erro ao processar dados básicos do PID {pid_str}: {e}")
            # Remove dados do cache se houve erro, para não usar dados inconsistentes na próxima vez
            if pid_str in cache['prev_times']: del cache['prev_times'][pid_str]
            if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str]
            continue
        except Exception as e: # pragma: no cover
            print(f"Erro inesperado ao processar PID {pid_str}: {e}")
            if pid_str in cache['prev_times']: del cache['prev_times'][pid_str]
            if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str]
            continue
            
    # Limpeza do cache: remove PIDs de processos que não existem mais
    stale_cpu_pids = set(cache['prev_times'].keys()) - active_pids_this_run
    for stale_pid in stale_cpu_pids:
        if stale_pid in cache['prev_times']: del cache['prev_times'][stale_pid] # pragma: no cover
    
    stale_io_pids = set(cache['prev_proc_io_stats'].keys()) - active_pids_this_run
    for stale_pid in stale_io_pids:
        if stale_pid in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][stale_pid] # pragma: no cover

    cache['prev_timestamp'] = now # Atualiza o timestamp da última coleta

    # Ordena os processos pelo tempo de CPU (maior primeiro) e limita a quantidade
    processes.sort(key=lambda x: x.get('cpu_time', 0), reverse=True)
    return processes[:limit]

def _parse_kb_value_from_status_line(value_str_with_unit):
    """
    Função auxiliar para converter uma string de memória (ex: '  123 kB') para um inteiro em KB.
    Usada para parsear valores do arquivo /proc/[pid]/status.

    Args:
        value_str_with_unit (str): A string contendo o valor e a unidade "kB".

    Returns:
        int: O valor em KB, ou 0 se a conversão falhar.
    """
    if isinstance(value_str_with_unit, str) and "kb" in value_str_with_unit.lower():
        try:
            return int(value_str_with_unit.lower().replace("kb", "").strip())
        except ValueError:
            return 0 # Retorna 0 se a conversão falhar
    return 0 # Retorna 0 se a string não estiver no formato esperado

def get_process_details(pid):
    """
    Obtém informações detalhadas para um processo específico, dado seu PID.
    Lê de /proc/[pid]/status e /proc/[pid]/stat.

    Args:
        pid (int): O ID do processo.

    Returns:
        dict or None: Um dicionário com detalhes do processo, ou None se o processo não for encontrado
                      ou se ocorrer um erro.
    """
    global CLK_TCK, PAGE_SIZE # Usa constantes globais
    try:
        proc_path = Path(f'/proc/{pid}')
        if not proc_path.exists(): return None # Processo não existe mais

        status_content = {} # Dicionário para armazenar dados do /proc/[pid]/status
        try:
            with open(proc_path / 'status', 'r') as f:
                for line in f:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        status_content[parts[0].strip()] = parts[1].strip()
        except FileNotFoundError: return None #(processo pode ter desaparecido)
        except Exception as e: 
            print(f"Erro ao ler /proc/{pid}/status para PID {pid}: {e}")
            return None

        # Extrai informações básicas do status_content
        name_val = status_content.get('Name', 'N/A')
        raw_state_val = status_content.get('State', 'N/A') # Estado bruto (ex: S (sleeping))

        uid_str_val = status_content.get('Uid', 'N/A N/A N/A N/A').split()[0] # Pega o primeiro UID (real)
        username_val = get_username_from_uid_local(int(uid_str_val)) if uid_str_val.isdigit() else 'N/A'
        
        threads_in_details = status_content.get('Threads', 'N/A')

        # Inicializa variáveis para dados do /proc/[pid]/stat
        nice_val_from_stat = "N/A"
        start_ticks_after_boot_val = "N/A"
        utime_ticks_val = 0
        stime_ticks_val = 0
        try:
            with open(proc_path / 'stat', 'r') as f_stat:
                stat_vals = f_stat.read().split()
            utime_ticks_val = int(stat_vals[13]) # Tempo de usuário
            stime_ticks_val = int(stat_vals[14]) # Tempo de kernel
            nice_val_from_stat = int(stat_vals[18]) # Valor Nice
            start_ticks_after_boot_val = int(stat_vals[21]) # Tempo de início em jiffies após o boot
        except (FileNotFoundError, IndexError, ValueError) as e: # pragma: no cover
            print(f"Aviso: Não foi possível ler alguns campos de /proc/{pid}/stat: {e}")

        # Traduz o valor 'nice' para uma prioridade legível
        translated_priority_val = _translate_priority_from_nice(nice_val_from_stat if isinstance(nice_val_from_stat, int) else None)
        # Calcula o tempo total de CPU em segundos
        cpu_time_seconds = round((utime_ticks_val + stime_ticks_val) / CLK_TCK, 2)

        # Calcula o horário de início do processo
        process_start_str = "N/A"
        system_boot_time_epoch = 0
        if isinstance(start_ticks_after_boot_val, int): #(assume start_ticks_after_boot_val será int se lido)
            try:
                # Lê o tempo de boot do sistema de /proc/stat
                with open('/proc/stat', 'r') as f_sys_stat:
                    for line in f_sys_stat:
                        if line.startswith('btime'): # Linha 'btime' contém o tempo de boot em segundos desde a Epoch
                            system_boot_time_epoch = int(line.split()[1])
                            break
            except (FileNotFoundError, ValueError) as e: 
                print(f"Aviso: Não foi possível ler o tempo de boot do sistema: {e}")
            
            if system_boot_time_epoch > 0:
                process_start_epoch = system_boot_time_epoch + (start_ticks_after_boot_val / CLK_TCK)
                process_start_str = datetime.fromtimestamp(process_start_epoch).strftime('%d/%m/%Y %H:%M:%S')
            else: # pragma: no cover
                # Fallback se o tempo de boot não puder ser determinado
                process_start_str = f"{(start_ticks_after_boot_val / CLK_TCK):.2f}s após o boot"

        # Informações de memória do processo
        vm_rss_str = status_content.get('VmRSS', '0 kB')        # Memória Residente
        vm_size_str = status_content.get('VmSize', '0 kB')       # Memória Virtual
        rss_shmem_str = status_content.get('RssShmem', '0 kB')   # Memória Residente Compartilhada

        # Converte valores de memória para KB para cálculo de páginas
        vm_rss_kb = _parse_kb_value_from_status_line(vm_rss_str)
        vm_size_kb = _parse_kb_value_from_status_line(vm_size_str)
        vm_exe_kb = _parse_kb_value_from_status_line(status_content.get('VmExe', '0 kB'))    # Memória do código executável
        vm_data_kb = _parse_kb_value_from_status_line(status_content.get('VmData', '0 kB'))  # Memória de dados + heap
        vm_stk_kb = _parse_kb_value_from_status_line(status_content.get('VmStk', '0 kB'))    # Memória da stack

        # Calcula a quantidade de páginas de memória (se PAGE_SIZE for válido)
        total_pages_resident = int(vm_rss_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'
        total_pages_virtual = int(vm_size_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'
        code_pages = int(vm_exe_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'
        data_heap_pages = int(vm_data_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'
        stack_pages = int(vm_stk_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'
        
        # VmData original para "Memória Gravável" (Data + BSS + Heap)
        vm_data_str = status_content.get('VmData', '0 kB')

        # Monta o dicionário de detalhes a ser retornado
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
            'Nice': nice_val_from_stat
        }
        return details_to_return

    except FileNotFoundError: #(processo não existe mais ao tentar abrir o diretório)
        return None
    except Exception as e: 
        print(f"Erro inesperado ao obter detalhes para PID {pid}: {e}")
        return None

def _translate_priority_from_nice(nice_value):
    """
    Converte um valor 'nice' numérico para uma descrição textual da prioridade.
    Valores 'nice' variam de -20 (maior prioridade) a 19 (menor prioridade).

    Args:
        nice_value (int or None): O valor nice do processo.

    Returns:
        str: Descrição textual da prioridade ou "N/A" se o valor for inválido.
    """
    if not isinstance(nice_value, int):
        return "N/A"
    
    if nice_value <= -15:
        return "Muito Alta"
    elif nice_value <= -1:
        return "Alta"
    elif nice_value == 0:
        return "Normal"
    elif nice_value <= 10:
        return "Baixa"
    elif nice_value <= 19:
        return "Muito Baixa"
    else: 
        return "Desconhecida"