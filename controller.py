import threading
import time
from pathlib import Path

from model_system import get_global_info, get_processes_info, get_process_details
from model_file import get_filesystem_info, get_directory_contents

class SystemData:
    """
    Classe para armazenar e gerenciar os dados do sistema (informações globais e lista de processos).
    Utiliza um `threading.Lock` para garantir a segurança do acesso e modificação dos dados
    em ambientes multithread, prevenindo condições de corrida.
    """
    def __init__(self, limit=10):
        """
        Inicializa a instância SystemData.

        Args:
            limit (int): O número máximo de processos a serem armazenados na lista `self.processes`.
        """
        self.lock = threading.Lock()
        self.global_info = {
            "CPU (%)": 0.0,
            "CPU ocioso (%)": 0.0,
            "Memória Usada (KB)": 0,
            "Memória (%)": 0.0,
            "Memória Livre (%)": 0.0,
            "Total de Processos": 0,
            "Total de Threads": 0,
            "Leitura Disco (B/s)": 0.0,
            "Escrita Disco (B/s)": 0.0
        }
        self.processes = []
        self.filesystem_info = {}
        self.limit = limit
        self.current_directory_path = "/"
        self.directory_contents = []

    def update(self):
        """
        Atualiza as informações globais, a lista de processos e as informações do sistema de arquivos.
        """
        try:
            infos = get_global_info()
            procs = get_processes_info(self.limit)

            fs_info = get_filesystem_info()
            dir_contents = get_directory_contents(self.current_directory_path)

            with self.lock:
                self.global_info = infos
                self.processes = procs
                self.filesystem_info = fs_info
                self.directory_contents = dir_contents
        except Exception as e:
            print(f"[ERRO] Falha ao atualizar dados: {e}")

    def get_snapshot(self):
        """
        Retorna uma cópia instantânea (snapshot) dos dados atuais do sistema.
        """
        with self.lock:
            current_global_info = self.global_info.copy()
            current_processes = list(self.processes)
            current_filesystem_info = self.filesystem_info.copy()
            current_directory_contents = list(self.directory_contents)
            current_path = self.current_directory_path
        return current_global_info, current_processes, current_filesystem_info, current_directory_contents, current_path

    def set_current_directory_path(self, path):
        """
        Define o caminho do diretório atual para a navegação do sistema de arquivos.
        Atualiza o caminho apenas se for um diretório válido e acessível.
        """
        with self.lock:
            if Path(path).is_dir():
                self.current_directory_path = path
            else:
                print(f"Caminho inválido ou não é um diretório: {path}")


system_data = SystemData()

_thread_started = False

def background_data_collector(interval):
    """
    Função alvo que será executada pela thread de coleta de dados.
    """
    while True:
        system_data.update()
        time.sleep(interval)

def start_background_thread(interval=5, limit=10):
    """
    Inicia a thread de coleta de dados em background, se ela ainda não tiver sido iniciada.
    """
    global _thread_started

    system_data.limit = limit

    if not _thread_started:
        thread = threading.Thread(
            target=background_data_collector,
            args=(interval,),
            daemon=True
        )
        thread.start()
        _thread_started = True