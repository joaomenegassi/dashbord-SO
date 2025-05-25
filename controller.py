# controller.py

import threading  # Importa o módulo para trabalhar com threads
import time       # Importa o módulo para manipulação de tempo (ex: time.sleep)
from model import get_global_info, get_processes_info  # Importa funções do módulo 'model' para obter dados do sistema

class SystemData:
    """
    Classe para armazenar e gerenciar os dados do sistema (informações globais e lista de processos).
    Utiliza um Lock para garantir a segurança em ambientes multithread.
    """
    def __init__(self, limit=10):
        """
        Inicializa a instância SystemData.

        Args:
            limit (int): O número máximo de processos a serem armazenados na lista. Padrão é 10.
        """
        self.lock = threading.Lock()  # Cria um Lock para sincronizar o acesso aos dados compartilhados
        # Inicializa o dicionário para informações globais do sistema com valores padrão
        self.global_info = {
            "CPU (%)": 0.0,
            "CPU ocioso (%)": 0.0,
            "Memória Usada (KB)": 0,
            "Memória (%)": 0.0,
            "Memória Livre (%)": 0.0,
            "Swap Total (KB)": 0,
            "Swap Usada (KB)": 0,
            "Swap Usada (%)": 0.0,
            "Total de Processos": 0,
            "Total de Threads": 0,
            "Leitura Disco (B/s)": 0.0,
            "Escrita Disco (B/s)": 0.0
        }
        self.processes = []  # Inicializa a lista de processos como vazia
        self.limit = limit   # Define o limite de processos a serem buscados

    def update(self):
        """
        Atualiza as informações globais e a lista de processos.
        Este método é chamado periodicamente pela thread de coleta de dados.
        Ele busca os dados mais recentes do sistema usando as funções do 'model'.
        """
        try:
            # Obtém as informações globais e dos processos do módulo 'model'
            infos = get_global_info()
            procs = get_processes_info(self.limit)  # Passa o limite atual para a função

            # Adquire o lock para garantir que a atualização dos dados seja atômica (thread-safe)
            with self.lock:
                self.global_info = infos
                self.processes = procs
        except Exception as e:
            # Em caso de erro durante a coleta ou processamento dos dados, imprime uma mensagem de erro.
            # Isso evita que a thread de coleta de dados pare inesperadamente.
            print(f"[ERRO] Falha ao atualizar dados: {e}")

    def get_snapshot(self):
        """
        Retorna uma cópia instantânea (snapshot) dos dados atuais do sistema.
        Utiliza o lock para garantir que a leitura dos dados seja segura em ambiente multithread
        e retorna cópias para evitar modificações externas nos dados internos.

        Returns:
            tuple: Uma tupla contendo (dicionário de informações globais, lista de processos).
        """
        with self.lock:  # Adquire o lock para ler os dados de forma segura
            # Cria cópias dos dados para evitar que modificações externas afetem o estado interno
            # ou que a thread de atualização modifique os dados enquanto estão sendo lidos.
            current_global_info = self.global_info.copy()
            current_processes = list(self.processes) # Cria uma cópia rasa da lista
        return current_global_info, current_processes

# Instância global da classe SystemData para ser usada em todo o módulo (e por app.py)
system_data = SystemData()

# Flag global para controlar se a thread de coleta de dados já foi iniciada.
# Isso garante que a thread seja iniciada apenas uma vez.
_thread_started = False

def background_data_collector(interval):
    """
    Função alvo para a thread de coleta de dados.
    Executa em um loop infinito, atualizando os dados do sistema em intervalos regulares.

    Args:
        interval (int): O intervalo em segundos entre as atualizações de dados.
    """
    while True:  # Loop infinito para coleta contínua de dados
        system_data.update()  # Chama o método update da instância global system_data
        time.sleep(interval)  # Aguarda o próximo intervalo

def start_background_thread(interval=5, limit=10):
    """
    Inicia a thread de coleta de dados em background, se ainda não tiver sido iniciada.
    Também atualiza o limite de processos que a thread de coleta deve buscar.

    Args:
        interval (int): O intervalo em segundos para a coleta de dados. Padrão é 5 segundos.
                        (Nota: Em app.py, este valor é sobrescrito para 2 segundos).
        limit (int): O número máximo de processos a serem listados. Padrão é 10.
    """
    global _thread_started  # Declara que estamos usando a variável global _thread_started

    # Atualiza o limite de processos no objeto system_data.
    # Isso permite que o número de processos exibidos seja dinamicamente ajustado pela UI.
    system_data.limit = limit

    # Verifica se a thread já foi iniciada para evitar criar múltiplas threads.
    if not _thread_started:
        # Cria uma nova thread.
        # 'target' é a função que a thread executará (background_data_collector).
        # 'args' são os argumentos para a função target (o intervalo de coleta).
        # 'daemon=True' significa que a thread será encerrada automaticamente quando o programa principal terminar.
        thread = threading.Thread(
            target=background_data_collector,
            args=(interval,),
            daemon=True
        )
        thread.start()  # Inicia a execução da thread
        _thread_started = True # Define a flag para True para indicar que a thread foi iniciada