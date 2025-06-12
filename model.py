import time
from pathlib import Path 
from datetime import datetime

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
    # Verifica primeiro se o UID já está no cache para economizar leituras de arquivo.
    if uid_int in _user_cache: # verifica se o UID já está no cache
        return _user_cache[uid_int] # Retorna o nome de usuário do cache.
    
    try:
        # Abre o arquivo /etc/passwd para leitura. Encoding utf-8 é uma boa prática para compatibilidade.
        with open('/etc/passwd', 'r', encoding='utf-8') as f: 
            # Itera sobre cada linha do arquivo.
            for line in f:
                # Remove espaços em branco no início/fim da linha e divide a linha pelo delimitador ':'
                # O formato padrão de uma linha em /etc/passwd é:
                # username:password_placeholder:UID:GID:GECOS_comment:home_directory:login_shell
                parts = line.strip().split(':') 
                # Verifica se a linha tem pelo menos 3 partes (nome, placeholder de senha, UID),
                # que são os campos mínimos necessários para obter o nome de usuário e UID.
                if len(parts) > 2: 
                    try:
                        # Compara o UID da linha (terceiro campo, parts[2]) com o UID procurado.
                        # Converte parts[2] para inteiro para a comparação.
                        if int(parts[2]) == uid_int: 
                            username = parts[0] # O nome de usuário é o primeiro campo (parts[0]).
                            _user_cache[uid_int] = username # Armazena o par UID-username no cache para futuras consultas.
                            return username # Retorna o nome de usuário encontrado.
                    except ValueError:
                        # Ignora linhas onde o UID (parts[2]) não é um número válido.
                        # Embora raro em um /etc/passwd bem formatado, é uma verificação de robustez.
                        continue 
    except FileNotFoundError:
        # Se o arquivo /etc/passwd não for encontrado (improvável em sistemas Linux funcionais,
        # mas bom para robustez, especialmente em ambientes containerizados ou customizados).
        # Armazena o UID como string no cache e o retorna.
        _user_cache[uid_int] = str(uid_int) 
        return str(uid_int)
    
    # Se o UID não for encontrado no arquivo após iterar por todas as linhas,
    # significa que não há um usuário correspondente no /etc/passwd.
    # Armazena o UID como string no cache e o retorna.
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
    current_timestamp = time.time() # Pega o timestamp atual para cálculos de delta de tempo.

    # --- Cálculo do Uso da CPU Global ---
    # Lê o arquivo /proc/stat, que contém estatísticas acumuladas do kernel, incluindo tempos de CPU.
    # A primeira linha ("cpu") resume os tempos da CPU para todos os cores.
    
    # Formato da linha "cpu": cpu  user nice system idle iowait irq softirq steal guest guest_nice
    # Os valores são em unidades de USER_HZ (jiffies), geralmente 1/100 de segundo.
    
    cpu_used_pct = 0.0 # Inicializa a porcentagem de CPU usada.
    cpu_ocioso_pct = 0.0 # Inicializa a porcentagem de CPU ociosa.
    try:
        with open('/proc/stat', 'r') as f: # Abre /proc/stat para leitura.
            line = f.readline() # Lê a primeira linha, que contém os dados agregados da CPU.
            # Converte os campos numéricos (após "cpu ") para inteiros.
            fields = list(map(int, line.split()[1:])) # Pega todos os valores após "cpu", converte para int.
        
        # idle: tempo em que a CPU estava ociosa (campo 4, índice 3).
        # iowait: tempo em que a CPU estava esperando por I/O (campo 5, índice 4).
        # Somamos ambos para ter o tempo total ocioso.
        current_ocioso = fields[3] + fields[4] # Tempo ocioso atual.
        current_total = sum(fields) # Tempo total da CPU (soma de todos os campos).
        
        # Pega os valores anteriores de idle e total do cache.
        prev_ocioso = cache['prev_sys_cpu_times'].get('ocioso', 0) 
        prev_total = cache['prev_sys_cpu_times'].get('total', 0) 

        # Calcula a diferença (delta) entre as leituras atuais e anteriores.
        if prev_total > 0 and current_total > prev_total: # Garante que temos dados anteriores válidos e o tempo avançou.
            total_diff = current_total - prev_total # Diferença total de ticks.
            ocioso_diff = current_ocioso - prev_ocioso   # Diferença de ticks ociosos.
            
            # % CPU Usada = (1 - (tempo ocioso no intervalo / tempo total no intervalo)) * 100
            # ocioso_diff/total_diff calcula a proporção do tempo total do intervalo em que a CPU esteve ociosa.
            cpu_used_pct = (1.0 - (ocioso_diff / total_diff)) * 100 if total_diff > 0 else 0.0 
            # % CPU Ociosa = (tempo ocioso no intervalo / tempo total no intervalo) * 100
            cpu_ocioso_pct = (ocioso_diff / total_diff) * 100 if total_diff > 0 else 0.0 
        else:
            # Fallback para a primeira leitura (quando não há `prev_total` ou se os contadores resetaram de alguma forma).
            # Calcula a % de uso baseada apenas na leitura atual (menos preciso, mas melhor que nada).
            # non_idle_time = user + nice + system + irq + softirq + steal
            non_ocioso_time = fields[0] + fields[1] + fields[2] + fields[5] + fields[6] + fields[7] 
            cpu_used_pct = (non_ocioso_time / current_total) * 100 if current_total > 0 else 0.0 
            cpu_ocioso_pct = (fields[3] / current_total * 100) if current_total > 0 else 0.0 # fields[3] é o 'idle' primário.
        

        # Atualiza o cache com os valores atuais para o próximo cálculo.
        cache['prev_sys_cpu_times']['ocioso'] = current_ocioso 
        cache['prev_sys_cpu_times']['total'] = current_total 

    except (FileNotFoundError, IndexError, ValueError, ZeroDivisionError) as e: # Trata possíveis erros de leitura.
        print(f"Erro ao ler /proc/stat: {e}") 

    # --- Cálculo do Uso da Memória RAM e SWAP ---
    # Lê o arquivo /proc/meminfo, que fornece informações detalhadas sobre o uso da memória.
    # Os valores são geralmente em KB.
    mem_used_pct = 0.0 # % de memória RAM usada.
    mem_free_pct = 0.0 # % de memória RAM livre.
    mem_used_absolute_kb = 0 # Memória RAM usada em KB.
    swap_total_kb = 0 # Total de memória SWAP em KB.
    swap_free_kb = 0  # Memória SWAP livre em KB.
    swap_used_kb = 0  # Memória SWAP usada em KB.

    try:
        meminfo = {} # Dicionário para armazenar os pares chave-valor de /proc/meminfo.
        with open('/proc/meminfo', 'r') as f: # Abre /proc/meminfo para leitura.
            for line in f:
                # Cada linha é no formato "Chave: Valor unidade" (ex: "MemTotal: 16384000 kB").
                chave, valor_str_com_unidade = line.split(':', 1) # Divide em chave e resto.
                # Pega apenas o valor numérico e converte para inteiro.
                meminfo[chave.strip()] = int(valor_str_com_unidade.split()[0]) 
        
        # MemTotal: Total de RAM física usável.
        total_mem_kb = meminfo.get('MemTotal', 1) # Usa 1 como fallback para evitar divisão por zero.
        # MemAvailable: Estimativa de quanta memória está disponível para iniciar novas aplicações,
        # sem fazer swap. É mais representativo da memória "livre" real do que MemFree.
        avail_mem_kb = meminfo.get('MemAvailable', meminfo.get('MemFree', 0)) 
        
        # Atualiza o cache com o total de memória se for a primeira vez ou se tiver mudado (improvável para MemTotal).
        if cache['mem_total_kb'] is None or cache['mem_total_kb'] != total_mem_kb: 
             cache['mem_total_kb'] = total_mem_kb 
        
        if total_mem_kb > 0: # Garante que total_mem_kb é positivo.
            # avail / total: proporção da memória RAM total do sistema que está atualmente disponível para ser utilizada por novas aplicações.
            # % Memória Usada = (1 - (Memória Disponível / Memória Total)) * 100
            mem_used_pct = (1.0 - (avail_mem_kb / total_mem_kb)) * 100 
            # % Memória Livre = (Memória Disponível / Memória Total) * 100
            mem_free_pct = (avail_mem_kb / total_mem_kb) * 100 
            # Memória Usada (absoluta) = Memória Total - Memória Disponível
            mem_used_absolute_kb = total_mem_kb - avail_mem_kb 
        else: # Caso total_mem_kb seja 0 ou negativo (improvável).
            mem_used_pct = 0.0 
            mem_free_pct = 0.0 
            mem_used_absolute_kb = 0 

        # Coleta de informações de Swap (memória virtual em disco).
        swap_total_kb = meminfo.get('SwapTotal', 0)
        swap_free_kb = meminfo.get('SwapFree', 0)   
        swap_used_kb = swap_total_kb - swap_free_kb 

    except (FileNotFoundError, ValueError, ZeroDivisionError) as e: # Trata erros de leitura/parse de /proc/meminfo.
        print(f"Erro ao ler /proc/meminfo: {e}") 
        # Define valores padrão em caso de erro para não quebrar a interface.
        mem_used_pct = 0.0 
        mem_free_pct = 0.0 
        mem_used_absolute_kb = 0 
        swap_used_kb = 0 # Garante valor padrão em caso de erro.

    # --- Contagem de Processos e Threads Totais no Sistema ---
    # Itera sobre os diretórios em /proc. Diretórios com nomes numéricos correspondem a PIDs.
    proc_count = 0 # Contador para o número total de processos.
    thread_count_global = 0 # Contador para o número total de threads no sistema.
    for proc_dir_global in Path('/proc').iterdir(): # Itera sobre todos os itens em /proc.
        # Verifica se o item é um diretório e se o nome do diretório é composto apenas por dígitos (é um PID).
        if proc_dir_global.is_dir() and proc_dir_global.name.isdigit(): 
            proc_count += 1 # Incrementa a contagem de processos.
            try:
                # Para cada processo, lê o arquivo /proc/[pid]/status para obter o número de threads.
                with open(proc_dir_global / 'status', 'r') as sf_global: # Abre /proc/[pid]/status.
                    for line_global in sf_global:
                        if line_global.startswith('Threads:'): # Procura a linha "Threads:".
                            thread_count_global += int(line_global.split()[1]) # Soma o número de threads deste processo ao total.
                            break # Sai do loop interno após encontrar a linha Threads.
            except (FileNotFoundError, PermissionError, ValueError): # Trata erros se o processo sumir ou não tiver permissão.
                # Se o arquivo status não puder ser lido (ex: processo terminou, permissão negada),
                # simplesmente continua para o próximo processo. A contagem de threads para este PID será ignorada.
                continue

    # --- Cálculo de I/O de Disco ---
    # Lê /proc/diskstats para obter estatísticas de I/O dos dispositivos de bloco (discos).
    # Os valores são acumulativos desde o boot.
    disk_read_bps = 0.0  # Taxa de leitura de disco em Bytes por Segundo.
    disk_write_bps = 0.0 # Taxa de escrita de disco em Bytes por Segundo.
    current_aggregated_reads_bytes = 0  # Total de bytes lidos de todos os discos relevantes nesta medição.
    current_aggregated_writes_bytes = 0 # Total de bytes escritos em todos os discos relevantes nesta medição.
    
    # Prefixos comuns para nomes de dispositivos de disco físico (ex: sda, hda, vda, xvda).
    relevant_device_prefixes = ('sd', 'hd', 'vd', 'xvd') 
    nvme_prefix = 'nvme' # Prefixo para discos NVMe (ex: nvme0n1).
    try:
        with open('/proc/diskstats', 'r') as f: # Abre /proc/diskstats.
            for line in f:
                fields = line.split() # Divide a linha em campos.
                # O formato de /proc/diskstats tem muitos campos. O nome do dispositivo é o 3º (índice 2).
                # Precisamos de pelo menos 10 campos para setores lidos (campo 6, índice 5) e escritos (campo 10, índice 9).
                if len(fields) < 10: continue # Pula linhas mal formatadas ou incompletas.
                device_name = fields[2] # Nome do dispositivo (ex: "sda", "nvme0n1").
                
                is_relevant = False # Flag para identificar se o dispositivo é um disco físico principal.
                # Verifica se o nome do dispositivo começa com um dos prefixos relevantes.
                for prefix in relevant_device_prefixes:
                    if device_name.startswith(prefix):
                        # Garante que é o dispositivo principal e não uma partição (ex: "sda" sim, "sda1" não).
                        # Faz isso verificando se não há dígitos após o prefixo.
                        if not any(char.isdigit() for char in device_name[len(prefix):]): #
                            is_relevant = True 
                        break # Sai do loop de prefixos.
                # Tratamento específico para NVMe: nvmeXnY (dispositivo) vs nvmeXnYpZ (partição).
                if not is_relevant and device_name.startswith(nvme_prefix):
                    # Se não contém 'p' após o prefixo "nvme", provavelmente é o dispositivo principal.
                    if 'p' not in device_name[len(nvme_prefix):]: 
                        is_relevant = True 
                
                # Exclui explicitamente dispositivos de CD/DVD (sr), loopback (loop), RAM disks (ram), device mapper (dm-).
                if device_name.startswith(('sr', 'loop', 'ram', 'dm-')): 
                    is_relevant = False 

                if is_relevant: # Se for um dispositivo de disco relevante.
                    try:
                        # Campo 6 (índice 5): setores lidos.
                        sectors_read = int(fields[5]) 
                        # Campo 10 (índice 9): setores escritos.
                        sectors_written = int(fields[9]) 
                        # Converte setores para bytes e acumula.
                        current_aggregated_reads_bytes += sectors_read * SECTOR_SIZE 
                        current_aggregated_writes_bytes += sectors_written * SECTOR_SIZE 
                    except ValueError: # Se a conversão para int falhar.
                        print(f"Aviso: Não foi possível parsear dados de I/O para o dispositivo {device_name}") 
                        continue 
    except (FileNotFoundError, IndexError) as e: # Trata erros de leitura/parse de /proc/diskstats.
        print(f"Erro ao ler ou processar /proc/diskstats: {e}") 

    # Calcula o tempo decorrido desde a última medição de I/O de disco.
    elapsed_disk_io_time = current_timestamp - cache.get('prev_disk_io_timestamp', current_timestamp - 1.0) 
    # Evita divisão por zero ou valores inflacionados se o tempo for muito pequeno.
    if elapsed_disk_io_time <= 0.001: 
        elapsed_disk_io_time = 1.0 # Usa 1 segundo como fallback.
    
    # Pega os totais de bytes lidos/escritos da medição anterior do cache.
    # Se não houver dados anteriores, usa os valores atuais (o delta será zero na primeira vez).
    prev_total_reads_bytes = cache.get('prev_disk_stats', {}).get('total_reads_bytes', current_aggregated_reads_bytes) 
    prev_total_writes_bytes = cache.get('prev_disk_stats', {}).get('total_writes_bytes', current_aggregated_writes_bytes) 

    # Calcula as taxas de I/O apenas se houve uma medição anterior significativa (evita picos na primeira amostragem).
    # A condição `cache.get('prev_disk_io_timestamp', current_timestamp) < (current_timestamp - 0.1)`
    # garante que houve uma medição anterior e que pelo menos 0.1s se passaram, para ter deltas mais estáveis.
    if cache.get('prev_disk_io_timestamp', current_timestamp) < (current_timestamp - 0.1) :
        read_diff_bytes = current_aggregated_reads_bytes - prev_total_reads_bytes # Delta de bytes lidos.
        write_diff_bytes = current_aggregated_writes_bytes - prev_total_writes_bytes # Delta de bytes escritos.
        
        # Taxa = Delta de Bytes / Delta de Tempo.
        disk_read_bps = read_diff_bytes / elapsed_disk_io_time 
        disk_write_bps = write_diff_bytes / elapsed_disk_io_time 

    # Atualiza o cache de I/O de disco com os valores agregados atuais e o timestamp.
    cache['prev_disk_stats'] = {
        'total_reads_bytes': current_aggregated_reads_bytes,
        'total_writes_bytes': current_aggregated_writes_bytes,
    } #
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
    processes = [] # Lista para armazenar os dicionários de informações dos processos.
    
    now = time.time() # Timestamp atual, para calcular `elapsed_wall_time`.
    # Calcula o tempo de parede (wall clock time) decorrido desde a última chamada desta função.
    # Usado para normalizar o uso de CPU do processo: (%CPU = Δtempo_cpu_processo / Δtempo_real_decorrido).
    # usa um fallback de 1.0 segundo para `elapsed_wall_time`.
    elapsed_wall_time = now - cache.get('prev_timestamp', now - 1.0) #
    # Evita divisão por zero ou taxas de CPU/I/O inflacionadas se o `elapsed_wall_time` for muito pequeno (ex: < 1ms).
    if elapsed_wall_time <= 0.001:
        elapsed_wall_time = 1.0

    # Garante que 'mem_total_kb' no cache esteja populado, se ainda não estiver.
    # Isso é necessário para calcular a % de memória usada por cada processo (mem_processo / mem_total_sistema).
    if cache['mem_total_kb'] is None: # geralmente populado por get_global_info
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'): # Procura a linha MemTotal.
                        cache['mem_total_kb'] = int(line.split()[1]) # Armazena o total de memória em KB no cache.
                        break
        except (FileNotFoundError, ValueError): # Trata erros de leitura.
            cache['mem_total_kb'] = 1

    mem_total_kb = cache.get('mem_total_kb', 1) # Pega do cache, ou 1 como fallback.
    if mem_total_kb == 0: mem_total_kb = 1 # guarda contra divisão por zero, caso o fallback acima falhe

    active_pids_this_run = set() # Conjunto para rastrear PIDs ativos encontrados nesta execução.
                                 # Usado no final para limpar PIDs "mortos" (que não existem mais) do cache.

    # Itera sobre os diretórios em /proc.
    for proc_dir in Path('/proc').iterdir():
        # Verifica se o nome do diretório é numérico (representando um PID).
        if not (proc_dir.is_dir() and proc_dir.name.isdigit()): 
            continue # Pula se não for um diretório de processo (ex: /proc/cpuinfo, /proc/meminfo).
        
        pid_str = proc_dir.name # PID como string (ex: "1234").
        pid_val = int(pid_str)  # PID como inteiro (ex: 1234).
        active_pids_this_run.add(pid_str) # Adiciona o PID (string) ao conjunto de PIDs ativos nesta varredura.
        
        try:
            # --- Leitura de /proc/[pid]/stat ---
            # Este arquivo contém informações de status do processo em um formato fixo, incluindo tempos de CPU.
            # Os tempos de CPU (utime, stime) são em 'jiffies' (clock ticks).
            with open(proc_dir / 'stat', 'r') as sf: # Abre /proc/[pid]/stat.
                vals = sf.readline().split() # Lê a linha única e divide em campos (valores).
            
            # O nome do processo é o segundo campo (índice 1), e está entre parênteses.
            # Pode conter espaços, então `strip('()')` remove os parênteses.
            name = vals[1].strip('()') 
            
            # utime: tempo de CPU gasto em modo usuário (campo 14, índice 13). Em jiffies.
            utime_ticks = int(vals[13]) 
            # stime: tempo de CPU gasto em modo kernel (campo 15, índice 14). Em jiffies.
            stime_ticks = int(vals[14]) 
            # Tempo total de CPU do processo (usuário + kernel) acumulado até esta medição.
            current_proc_total_ticks = utime_ticks + stime_ticks 

            # --- Leitura de /proc/[pid]/status ---
            # Este arquivo contém informações mais legíveis sobre o processo, como UID, memória (VmRSS), threads.
            # Os valores são em formato "Chave: Valor".
            uid_int = -1        # UID do processo (Real UID). Inicializa com -1 (inválido).
            mem_kb_val = 0      # Memória residente (VmRSS) em KB.
            num_threads = 0     # Número de threads do processo.
            try:
                with open(proc_dir / 'status', 'r') as sf_status: # Abre /proc/[pid]/status.
                    for line in sf_status:
                        if line.startswith('Uid:'): # Linha de User ID.
                            # A linha Uid tem 4 valores: Real, Effective, Saved Set, File System UIDs.
                            # Pegamos o primeiro (Real UID), que é o segundo token na linha (índice 1).
                            uid_int = int(line.split()[1]) 
                        elif line.startswith('VmRSS:'): # Resident Set Size: porção da memória do processo mantida na RAM.
                            mem_kb_str = line.split()[1] # Pega o valor (ex: "1234").
                            mem_kb_val = int(mem_kb_str) if mem_kb_str.isdigit() else 0 # Converte para int, ou 0 se não for dígito.
                        elif line.startswith('Threads:'): # Linha com número de threads.
                            num_threads = int(line.split()[1]) # Pega o número de threads.
            except FileNotFoundError:
                # Se o processo sumiu (arquivo não encontrado), remove seus dados do cache para evitar inconsistências.
                if pid_str in cache['prev_times']: del cache['prev_times'][pid_str] #
                if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str] 
                continue

            # Obtém nome de usuário a partir do UID, usando a função (que tem seu próprio cache).
            username = get_username_from_uid_local(uid_int) if uid_int != -1 else 'N/A'
            
            # --- Cálculo da porcentagem de CPU usada pelo processo ---
            # Pega os ticks totais da CPU da leitura anterior para este PID do cache.
            # Se for a primeira vez que vemos este PID, `prev_proc_ticks` será 0.
            prev_proc_ticks = cache['prev_times'].get(pid_str, 0) 
            # Diferença de ticks de CPU do processo (no intervalo), convertida para segundos.
            # (current_ticks - prev_ticks) / jiffies_por_segundo = segundos_de_cpu_no_intervalo.
            cpu_time_diff_seconds = (current_proc_total_ticks - prev_proc_ticks) / CLK_TCK 
            # % CPU = (tempo_cpu_usado_pelo_processo_no_intervalo / tempo_total_do_intervalo_real) * 100
            cpu_pct = (cpu_time_diff_seconds / elapsed_wall_time) * 100 
            
            # --- Cálculo do uso de memória pelo processo ---
            mem_mb = mem_kb_val / 1024.0 # Converte VmRSS de KB para MB (float).
            # % Memória = (memoria_usada_pelo_processo_KB / memoria_total_do_sistema_KB) * 100
            mem_pct = (mem_kb_val / mem_total_kb) * 100.0 if mem_total_kb > 0 else 0.0 
            
            # Tempo total de CPU acumulado pelo processo em segundos (desde que o processo iniciou).
            cpu_time_seconds = current_proc_total_ticks / CLK_TCK 
            
            # Armazena os ticks totais atuais deste processo no cache para o próximo cálculo de delta.
            cache['prev_times'][pid_str] = current_proc_total_ticks 
            
            # --- Cálculo de I/O por processo ---
            # Lê /proc/[pid]/io para obter bytes lidos/escritos pelo processo.
            io_read_bps = 0.0  # Taxa de leitura do processo em Bytes por Segundo.
            io_write_bps = 0.0 # Taxa de escrita do processo em Bytes por Segundo.
            try:
                # O arquivo /proc/[pid]/io contém contadores de I/O para o processo.
                with open(proc_dir / 'io', 'r') as f_io: # Abre /proc/[pid]/io.
                    current_proc_read_bytes = 0
                    current_proc_write_bytes = 0
                    for line in f_io:
                        if line.startswith('read_bytes:'): # Bytes lidos de dispositivos de armazenamento.
                            current_proc_read_bytes = int(line.split()[1]) 
                        elif line.startswith('write_bytes:'): # Bytes escritos em dispositivos de armazenamento.
                            current_proc_write_bytes = int(line.split()[1]) 
                
                # Pega as estatísticas de I/O anteriores para este PID do cache.
                prev_io_stats_for_pid = cache['prev_proc_io_stats'].get(pid_str) 
                if prev_io_stats_for_pid: # Se houver dados anteriores para este PID.
                    # Calcula a diferença de bytes lidos/escritos no intervalo.
                    read_bytes_diff = current_proc_read_bytes - prev_io_stats_for_pid['read_bytes'] 
                    write_bytes_diff = current_proc_write_bytes - prev_io_stats_for_pid['write_bytes'] 
                    # Calcula as taxas de I/O em bytes por segundo.
                    # Taxa = Delta Bytes / Delta Tempo Real.
                    io_read_bps = read_bytes_diff / elapsed_wall_time if elapsed_wall_time > 0 else 0 
                    io_write_bps = write_bytes_diff / elapsed_wall_time if elapsed_wall_time > 0 else 0 
                
                # Atualiza o cache de I/O do processo com os valores atuais para o próximo cálculo.
                cache['prev_proc_io_stats'][pid_str] = {
                    'read_bytes': current_proc_read_bytes,
                    'write_bytes': current_proc_write_bytes,
                } 
            except (FileNotFoundError, PermissionError, ValueError):
                pass 

            # Adiciona as informações do processo formatadas à lista `processes`.
            processes.append({
                'pid': pid_val, 
                'name': name, 
                'username': username, 
                'threads': num_threads, 
                'cpu_percent': round(max(0, cpu_pct), 2), # Garante que %CPU não seja negativo (pode ocorrer com flutuações pequenas). Arredonda.
                'memory_mb': round(mem_mb, 2), # Memória em MB, arredondada.
                'memory_percent': round(mem_pct, 2), # % Memória, arredondada.
                'cpu_time': round(cpu_time_seconds, 2), # Tempo total de CPU acumulado, arredondado.
                'io_read_bps': round(max(0, io_read_bps), 2), # Taxa de leitura, garante não negativo, arredonda.
                'io_write_bps': round(max(0, io_write_bps), 2)  # Taxa de escrita, garante não negativo, arredonda.
            })
            
        except FileNotFoundError: #(processo terminou durante a coleta dos dados deste PID)
            # Se o processo desapareceu (ex: /proc/[pid]/stat não encontrado),
            # limpa seus rastros do cache para não usar dados antigos na próxima vez que um PID similar aparecer.
            if pid_str in cache['prev_times']: del cache['prev_times'][pid_str] 
            if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str] 
            continue
        except (PermissionError, IndexError, ValueError) as e:
            # Erros comuns ao tentar ler arquivos de /proc para processos com restrições (ex: alguns processos kernel)
            # ou que sumiram muito rapidamente entre as leituras de arquivo.
            # IndexError pode ocorrer se a linha de /proc/[pid]/stat tiver menos campos que o esperado.
            # ValueError pode ocorrer se um campo esperado como numérico não for.
            print(f"Erro ao processar dados básicos do PID {pid_str}: {e}") 
            # Remove dados do cache se houve erro, para não usar dados inconsistentes na próxima vez.
            if pid_str in cache['prev_times']: del cache['prev_times'][pid_str] 
            if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str] 
            continue 
        except Exception as e:
            print(f"Erro inesperado ao processar PID {pid_str}: {e}") 
            # Limpa o cache para este PID em caso de erro genérico também.
            if pid_str in cache['prev_times']: del cache['prev_times'][pid_str] 
            if pid_str in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][pid_str] 
            continue 
            
    # --- Limpeza do cache: remove PIDs de processos que não existem mais ---
    # Compara as chaves do cache `prev_times` com os PIDs ativos (`active_pids_this_run`) encontrados nesta execução.
    # Aqueles PIDs que estão no cache mas não foram encontrados como ativos são "stale" (obsoletos).
    stale_cpu_pids = set(cache['prev_times'].keys()) - active_pids_this_run # PIDs no cache de CPU que não estão mais ativos.
    for stale_pid in stale_cpu_pids:
        if stale_pid in cache['prev_times']: del cache['prev_times'][stale_pid]
    
    # Faz o mesmo para o cache de I/O por processo.
    stale_io_pids = set(cache['prev_proc_io_stats'].keys()) - active_pids_this_run # PIDs no cache de I/O que não estão mais ativos.
    for stale_pid in stale_io_pids:
        if stale_pid in cache['prev_proc_io_stats']: del cache['prev_proc_io_stats'][stale_pid]

    # Atualiza o timestamp global da última coleta de dados de processos.
    # Este será o `prev_timestamp` para a próxima chamada desta função.
    cache['prev_timestamp'] = now 

    # Ordena a lista de processos. O critério principal é 'cpu_time' (tempo total de CPU acumulado),
    # de forma decrescente (os processos que mais usaram CPU acumulada aparecem primeiro).
    processes.sort(key=lambda x: x.get('cpu_time', 0), reverse=True) 
    # Retorna apenas o número de processos especificado pelo argumento `limit`.
    return processes[:limit] 

def _parse_kb_value_from_status_line(value_str_with_unit):
    """
    Função auxiliar para converter uma string de memória (ex: '  123 kB')
    lida do arquivo /proc/[pid]/status para um valor inteiro em Kilobytes (KB).

    Args:
        value_str_with_unit (str): A string contendo o valor e a unidade "kB"
                                   (ex: "1234 kB", "  5678  kB  ").

    Returns:
        int: O valor em KB. Retorna 0 se a conversão falhar, se a string não contiver "kb",
             ou se não for uma string.
    """
    # Verifica se é uma string e se contém "kb" (case-insensitive para robustez).
    if isinstance(value_str_with_unit, str) and "kb" in value_str_with_unit.lower(): 
        try:
            # Converte para minúsculas, remove "kb", remove espaços em branco ao redor,
            # e então converte para inteiro.
            return int(value_str_with_unit.lower().replace("kb", "").strip()) 
        except ValueError:
            # Se a conversão para inteiro falhar (ex: string vazia após remoção, ou contém outros caracteres).
            return 0
    return 0

def get_process_details(pid):
    """
    Obtém informações detalhadas para um processo específico, dado seu PID.
    Lê principalmente de /proc/[pid]/status para a maioria dos detalhes e complementa
    com informações de /proc/[pid]/stat (como 'nice', tempo de início, tempos de CPU).
    Também calcula o número de páginas de memória com base nos valores de VmRSS, VmSize, etc.

    Args:
        pid (int): O ID do processo para o qual obter detalhes.

    Returns:
        dict or None: Um dicionário com os detalhes do processo se encontrado e legível.
                      Retorna `None` se o processo com o PID especificado não for encontrado
                      ou se ocorrer um erro significativo ao ler seus dados.
    """
    global CLK_TCK, PAGE_SIZE # Usa constantes globais para cálculos (jiffies/seg e tamanho da página).
    try:
        # Constrói o caminho para o diretório do processo em /proc.
        proc_path = Path(f'/proc/{pid}') 
        # Verifica se o diretório do processo (e, portanto, o processo) existe.
        if not proc_path.exists(): return None # Processo não existe mais, retorna None.

        # --- Leitura de /proc/[pid]/status ---
        # Este arquivo contém informações de status em formato "Chave: Valor".
        status_content = {} # Dicionário para armazenar os dados chave-valor do arquivo status.
        try:
            with open(proc_path / 'status', 'r') as f:
                for line in f:
                    parts = line.split(":", 1) # Divide cada linha em "Chave" e "Valor" (o valor pode conter ':').
                    if len(parts) == 2: # Se a divisão foi bem-sucedida.
                        status_content[parts[0].strip()] = parts[1].strip() # Armazena no dicionário, removendo espaços.
        except FileNotFoundError: return None # Processo pode ter desaparecido entre o Path.exists() e aqui.
        except Exception as e:
            print(f"Erro ao ler /proc/{pid}/status para PID {pid}: {e}") 
            return None #

        # Extrai informações básicas do dicionário `status_content` (que foi populado de /proc/[pid]/status).
        name_val = status_content.get('Name', 'N/A') # Nome do processo. Usa 'N/A' se a chave não existir.
        raw_state_val = status_content.get('State', 'N/A') # Estado bruto do processo (ex: "S (sleeping)", "R (running)").

        # A linha 'Uid:' em /proc/[pid]/status tem 4 valores: Real, Effective, SavedSet, FileSystem UIDs.
        # Pegamos o primeiro (Real UID).
        uid_str_val = status_content.get('Uid', 'N/A N/A N/A N/A').split()[0] # Pega o primeiro UID da string.
        # Converte o UID para nome de usuário, se o UID for numérico.
        username_val = get_username_from_uid_local(int(uid_str_val)) if uid_str_val.isdigit() else 'N/A' 
        
        threads_in_details = status_content.get('Threads', 'N/A')

        # --- Leitura de /proc/[pid]/stat para complementar informações ---
        # /proc/[pid]/stat fornece:
        #   - utime (campo 14, índice 13): tempo de CPU em modo usuário (jiffies).
        #   - stime (campo 15, índice 14): tempo de CPU em modo kernel (jiffies).
        #   - nice (campo 19, índice 18): valor 'nice' do processo.
        #   - starttime (campo 22, índice 21): tempo de início do processo em jiffies após o boot do sistema.
        nice_val_from_stat = "N/A"                # Valor 'nice' do processo.
        start_ticks_after_boot_val = "N/A"        # Tempo de início do processo em jiffies após o boot.
        utime_ticks_val = 0                       # Tempo de CPU em modo usuário (jiffies), default 0.
        stime_ticks_val = 0                       # Tempo de CPU em modo kernel (jiffies), default 0.
        try:
            with open(proc_path / 'stat', 'r') as f_stat:
                stat_vals = f_stat.read().split() # Lê todos os campos.
            utime_ticks_val = int(stat_vals[13]) # utime é o 14º campo (índice 13).
            stime_ticks_val = int(stat_vals[14]) # stime é o 15º campo (índice 14).
            nice_val_from_stat = int(stat_vals[18]) # nice é o 19º campo (índice 18).
            start_ticks_after_boot_val = int(stat_vals[21]) # starttime é o 22º campo (índice 21).
        except (FileNotFoundError, IndexError, ValueError) as e:
            print(f"Aviso: Não foi possível ler alguns campos de /proc/{pid}/stat: {e}") 

        # Traduz o valor 'nice' numérico para uma prioridade legível (ex: "Normal", "Alta").
        translated_priority_val = _translate_priority_from_nice(nice_val_from_stat if isinstance(nice_val_from_stat, int) else None) 
        # Calcula o tempo total de CPU acumulado pelo processo em segundos.
        cpu_time_seconds = round((utime_ticks_val + stime_ticks_val) / CLK_TCK, 2) 

        # --- Calcula o horário de início do processo ---
        process_start_str = "N/A" # String formatada para o horário de início (dd/mm/yyyy HH:MM:SS).
        system_boot_time_epoch = 0  # Tempo de boot do sistema em segundos desde a Epoch (1/1/1970 UTC).
        if isinstance(start_ticks_after_boot_val, int):
            try:
                # Lê o tempo de boot do sistema de /proc/stat (linha que começa com 'btime').
                # 'btime' é o tempo de boot em segundos desde a Epoch.
                with open('/proc/stat', 'r') as f_sys_stat: # Abre /proc/stat (do sistema).
                    for line in f_sys_stat:
                        if line.startswith('btime'): # Linha 'btime' contém o tempo de boot em segundos desde a Epoch.
                            system_boot_time_epoch = int(line.split()[1]) # Pega o valor numérico.
                            break
            except (FileNotFoundError, ValueError) as e:
                print(f"Aviso: Não foi possível ler o tempo de boot do sistema: {e}") 
            
            if system_boot_time_epoch > 0: # Se o tempo de boot foi obtido com sucesso.
                # Calcula o timestamp de início do processo:
                # boot_time_epoch (segundos) + (start_ticks_do_processo_apos_boot / jiffies_por_segundo)
                process_start_epoch = system_boot_time_epoch + (start_ticks_after_boot_val / CLK_TCK) 
                # Formata o timestamp epoch para uma string de data/hora legível.
                process_start_str = datetime.fromtimestamp(process_start_epoch).strftime('%d/%m/%Y %H:%M:%S') 
            else:
                # Se não foi possível obter `btime`, mostra o tempo de início como "X.YZs após o boot".
                process_start_str = f"{(start_ticks_after_boot_val / CLK_TCK):.2f}s após o boot" 

        # --- Informações de memória do processo (de /proc/[pid]/status) ---
        # VmRSS: Resident Set Size - porção da memória do processo mantida na RAM.
        vm_rss_str = status_content.get('VmRSS', '0 kB')
        # VmSize: Virtual Memory Size - tamanho total do espaço de endereçamento virtual do processo.
        vm_size_str = status_content.get('VmSize', '0 kB')    
        # RssShmem: Porção da VmRSS que é memória compartilhada com outros processos.
        rss_shmem_str = status_content.get('RssShmem', '0 kB') 

        # Converte valores de memória (que vêm como strings "xxx kB" de /proc/[pid]/status)
        # para inteiros em KB usando a função auxiliar `_parse_kb_value_from_status_line`.
        # Isso é necessário para o cálculo do número de páginas.
        vm_rss_kb = _parse_kb_value_from_status_line(vm_rss_str)
        vm_size_kb = _parse_kb_value_from_status_line(vm_size_str)
        # VmExe: Memória usada pelo código executável (segmento de texto).
        vm_exe_kb = _parse_kb_value_from_status_line(status_content.get('VmExe', '0 kB')) 
        # VmData: Memória usada por dados inicializados/não inicializados + heap (segmento de dados).
        vm_data_kb = _parse_kb_value_from_status_line(status_content.get('VmData', '0 kB')) 
        # VmStk: Memória usada pela(s) stack(s) do processo.
        vm_stk_kb = _parse_kb_value_from_status_line(status_content.get('VmStk', '0 kB')) 

        # Calcula a quantidade de páginas de memória.
        # Uma página de memória tem PAGE_SIZE bytes. Convertemos KB para Bytes (KB * 1024)
        # e dividimos pelo PAGE_SIZE para obter o número de páginas.
        # Se PAGE_SIZE for 0 ou inválido, retorna 'N/A'.
        total_pages_resident = int(vm_rss_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A' # Páginas residentes.
        total_pages_virtual = int(vm_size_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'  # Páginas virtuais totais.
        code_pages = int(vm_exe_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'           # Páginas de código (VmExe).
        data_heap_pages = int(vm_data_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'    # Páginas de dados/heap (VmData).
        stack_pages = int(vm_stk_kb * 1024 / PAGE_SIZE) if PAGE_SIZE > 0 else 'N/A'          # Páginas de stack (VmStk).
        
        # VmData original (string com "kB", ex: "4321 kB") para exibição como "Memória Gravável".
        vm_data_str = status_content.get('VmData', '0 kB')

        # Monta o dicionário de detalhes a ser retornado para a view.
        # Mantém as strings originais com "kB" para alguns campos de memória, pois a view
        # pode ter funções de formatação específicas para elas (ex: `format_memory_from_status`).
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
        return details_to_return # Retorna o dicionário com todos os detalhes coletados.

    except FileNotFoundError: # Se o diretório /proc/[pid] não foi encontrado inicialmente (antes de abrir /status).
        return None 
    except Exception as e: # Captura qualquer outro erro inesperado durante a coleta de detalhes para este PID.
        print(f"Erro inesperado ao obter detalhes para PID {pid}: {e}") 
        return None 

def _translate_priority_from_nice(nice_value):
    """
    Converte um valor 'nice' numérico (de -20 a 19) para uma descrição textual da prioridade do processo.
    Valores 'nice' em Linux:
      -20: Maior prioridade para o processo (mais favorecido pelo scheduler).
        0: Prioridade padrão/normal.
       19: Menor prioridade para o processo (menos favorecido).
    A prioridade real do kernel é frequentemente calculada como `nice + 20` (resultando em 0 a 39 internamente,
    onde 0 é a mais alta). Esta função mapeia faixas de 'nice' para descrições amigáveis.

    Args:
        nice_value (int or None): O valor nice do processo. Pode ser None se a leitura de /proc/[pid]/stat falhou.

    Returns:
        str: Descrição textual da prioridade (ex: "Muito Alta", "Normal", "Baixa")
             ou "N/A" se o `nice_value` for inválido ou None.
    """
    if not isinstance(nice_value, int): # Verifica se nice_value é um inteiro.
        return "N/A" # Se nice_value não for um inteiro (ex: None ou string "N/A" passada).
    
    if nice_value <= -15: # Prioridade muito alta (nice de -20 a -15)
        return "Muito Alta" 
    elif nice_value <= -1:  # Prioridade alta (nice de -14 a -1)
        return "Alta" 
    elif nice_value == 0:   # Prioridade normal (nice = 0)
        return "Normal" 
    elif nice_value <= 10:  # Prioridade baixa (nice de 1 a 10)
        return "Baixa" 
    elif nice_value <= 19:  # Prioridade muito baixa (nice de 11 a 19)
        return "Muito Baixa" 
    else: # Valores fora da faixa esperada de -20 a 19 (embora incomum para 'nice' padrão).
        return "Desconhecida" 